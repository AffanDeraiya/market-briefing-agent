"""App entry: ties agents + API together (techspec §9)."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from src.api.guards import daily_counter
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

    _app.state.limiter = limiter
    _app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    _app.include_router(router)

    @_app.get("/api/health")
    def health() -> dict[str, str | int]:
        return {
            "status": "ok",
            "model": os.environ.get("LLM_MODEL", "unconfigured"),
            "daily_briefs_remaining": daily_counter.remaining(),
        }

    return _app


app = create_app()
