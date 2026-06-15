"""FastAPI router — /api/brief and /api/validate/{ticker}."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slowapi.util import get_remote_address
from sse_starlette.sse import EventSourceResponse

from src.agents.market_brief.state import Period
from src.agents.market_brief.utils.market_data import (
    TickerNotFoundError,
    get_fundamentals,
)
from src.agents.market_brief.utils.symbols import search_symbols

from .guards import (
    daily_counter,
    inflight,
    normalize_ticker,
    rate_limit_per_day,
    rate_limit_per_hour,
    search_rate_limit,
    validate_rate_limit,
)
from .limiter import limiter
from .sse import brief_event_stream

__all__ = ["router"]

router = APIRouter()


class BriefRequest(BaseModel):
    ticker: str
    period: Period = "3mo"


def _rate_limit_string() -> str:
    """Per-IP hourly slowapi limit string; read from env per-request so tests can override."""
    return f"{rate_limit_per_hour()}/hour"


def _daily_limit_string() -> str:
    """Return per-IP daily slowapi limit string; read from env per-request so tests can override."""
    return f"{rate_limit_per_day()}/day"


# Two stacked @limiter.limit decorators apply both an hourly AND a daily per-IP cap.
# slowapi evaluates all stacked limits; the first one that fires returns 429.
@router.post("/api/brief")
@limiter.limit(_rate_limit_string)
@limiter.limit(_daily_limit_string)
async def post_brief(request: Request, body: BriefRequest) -> EventSourceResponse:
    """Stream a market brief as Server-Sent Events."""
    try:
        ticker = normalize_ticker(body.ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not daily_counter.try_consume():
        raise HTTPException(
            status_code=429,
            detail={"kind": "budget", "message": "global daily limit reached"},
        )

    # Enforce in-flight (concurrency) caps AFTER consuming the daily slot so
    # that we can refund it cleanly if the cap is already reached.
    ip = get_remote_address(request)
    if not inflight.try_acquire(ip):
        # Refund the daily slot — this request will not produce a brief.
        daily_counter.refund()
        raise HTTPException(
            status_code=429,
            detail={
                "kind": "concurrency",
                "message": "too many concurrent briefs; try again shortly",
            },
        )

    # Pass the client IP into the stream so it can release the inflight slot on exit.
    return EventSourceResponse(brief_event_stream(ticker, body.period, ip))


# slowapi requires `request: Request` as the FIRST parameter on rate-limited endpoints.
@router.get("/api/search")
@limiter.limit(search_rate_limit)
async def search_symbols_endpoint(request: Request, q: str = "") -> dict[str, object]:
    """Return up to 8 ticker suggestions for a free-text query (autocomplete)."""
    return {"results": [s.model_dump() for s in search_symbols(q)]}


@router.get("/api/validate/{ticker}")
@limiter.limit(validate_rate_limit)
async def validate_ticker(request: Request, ticker: str) -> dict[str, object]:
    """Validate a ticker symbol and return basic info."""
    try:
        clean = normalize_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        f = get_fundamentals(clean)
        return {
            "valid": True,
            "ticker": clean,
            "name": f.name,
            "exchange": f.exchange,
        }
    except TickerNotFoundError:
        return {"valid": False, "ticker": clean, "name": None, "exchange": None}
    except Exception:  # noqa: BLE001
        return {"valid": False, "ticker": clean, "name": None, "exchange": None}
