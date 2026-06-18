"""App entry: ties agents + API together (techspec §9).

Proxy-header note (fix #4)
--------------------------
When deployed behind a trusted reverse proxy (Render, Vercel, nginx, etc.)
the real client IP arrives in the X-Forwarded-For header.  Uvicorn must be
started with ``--proxy-headers --forwarded-allow-ips='*'`` so that Starlette
populates ``request.client.host`` (and therefore ``get_remote_address``) with
the forwarded IP rather than the proxy's own address.

Use the ``make serve-prod`` Makefile target, which passes these flags
automatically.  Never use this flag set in development when there is no
trusted proxy in front, as it allows clients to spoof their IP.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from src.api.guards import daily_counter, rate_limit_per_hour
from src.api.limiter import limiter
from src.api.routes import router

__all__ = ["app", "create_app"]


def _rate_limit_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a structured 429 for per-IP slowapi rate limit hits."""
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "kind": "rate_limit",
                "message": "per-IP hourly limit reached",
                "retry_after_s": 3600,
            }
        },
    )


def create_app() -> FastAPI:
    """Build and return a fully configured FastAPI application."""
    load_dotenv()

    # Route market_brief.* log records to uvicorn's logger so they appear in the terminal
    # alongside normal uvicorn output without any extra --log-level flags.
    _mb_log = logging.getLogger("market_brief")
    _mb_log.setLevel(logging.DEBUG)
    if not _mb_log.handlers:
        _handler = logging.StreamHandler()
        _handler.setFormatter(logging.Formatter("%(levelname)s  %(name)s  %(message)s"))
        _mb_log.addHandler(_handler)
        _mb_log.propagate = False

    _app = FastAPI(title="Market Briefing Agent")

    # CORS — comma-separated origins from env; default to the Vite dev server
    raw_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    _app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Security headers (fix #9) ─────────────────────────────────────────
    # Applied to every response.  CSP is intentionally omitted: the backend
    # serves JSON/SSE plus /docs (Swagger UI), and a CSP would break Swagger.
    @_app.middleware("http")
    async def add_security_headers(request: Request, call_next: object) -> Response:
        response: Response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response

    _app.state.limiter = limiter
    _app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    _app.include_router(router)

    @_app.get("/api/health")
    def health() -> dict[str, str | int]:
        return {
            "status": "ok",
            "model": os.environ.get("LLM_MODEL", "unconfigured"),
            "daily_briefs_remaining": daily_counter.remaining(),
            "briefs_per_hour": rate_limit_per_hour(),
        }

    return _app


app = create_app()
