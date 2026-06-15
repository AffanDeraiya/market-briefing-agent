# Backend container — FastAPI + SSE agent (techspec §9).
# Multi-stage: deps install cached separately from source for fast rebuilds.
# Render injects $PORT at runtime; we bind to it (default 8000 for local docker run).

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# uv (pinned binary copied from the official image)
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

WORKDIR /app

# 1) Install dependencies first so this layer is cached unless the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 2) Copy application source.
COPY . .

EXPOSE 8000

# Shell form so ${PORT} expands at runtime. --proxy-headers makes slowapi see the
# real client IP via X-Forwarded-For behind Render's proxy (see src/main.py docstring).
CMD uv run uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000} \
    --proxy-headers --forwarded-allow-ips='*'
