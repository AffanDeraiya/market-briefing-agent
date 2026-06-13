"""FastAPI router — /api/brief and /api/validate/{ticker}."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.agents.market_brief.state import Period
from src.agents.market_brief.utils.market_data import (
    TickerNotFoundError,
    get_fundamentals,
)

from .guards import daily_counter, normalize_ticker, rate_limit_per_hour
from .limiter import limiter
from .sse import brief_event_stream

__all__ = ["router"]

router = APIRouter()


class BriefRequest(BaseModel):
    ticker: str
    period: Period = "3mo"


def _rate_limit_string() -> str:
    """Return slowapi limit string, read from env per-request so tests can override."""
    return f"{rate_limit_per_hour()}/hour"


@router.post("/api/brief")
@limiter.limit(_rate_limit_string)
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

    return EventSourceResponse(brief_event_stream(ticker, body.period))


@router.get("/api/validate/{ticker}")
async def validate_ticker(ticker: str) -> dict[str, object]:
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
