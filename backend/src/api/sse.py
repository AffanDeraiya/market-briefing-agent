"""Sync→async bridge: runs the agent in a worker thread and yields SSE dicts."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from src.agents.market_brief.agent import RunResult, run_agent
from src.agents.market_brief.events import EVENT_ERROR
from src.llm import get_backend

__all__ = ["brief_event_stream", "log_run"]

_log = logging.getLogger("market_brief.run")


def log_run(
    ticker: str,
    period: str,
    result_usage: dict[str, Any],
    outcome: str,
) -> None:
    """Emit one JSON log line for a completed run."""
    _log.info(
        json.dumps(
            {
                "event": "run_complete",
                "ticker": ticker,
                "period": period,
                "outcome": outcome,
                **result_usage,
            },
            ensure_ascii=False,
        )
    )


async def brief_event_stream(ticker: str, period: str) -> AsyncIterator[dict[str, str]]:
    """Run the agent in a worker thread and yield SSE dicts {event, data} as it emits."""
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | object] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    sentinel: object = object()

    def emit(event_type: str, data: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, (event_type, data))

    def worker() -> None:
        result: RunResult | None = None
        try:
            backend = get_backend()
            result = run_agent(ticker, period, backend=backend, emit=emit)
        except Exception as exc:  # noqa: BLE001
            emit(EVENT_ERROR, {"kind": "internal", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            if result is not None:
                outcome = "error" if result.error else "ok"
                log_run(ticker, period, result.usage, outcome)
            loop.call_soon_threadsafe(queue.put_nowait, sentinel)

    task = asyncio.create_task(asyncio.to_thread(worker))
    try:
        while True:
            item = await queue.get()
            if item is sentinel:
                break
            event_type, data = item  # type: ignore[misc]
            yield {"event": event_type, "data": json.dumps(data, ensure_ascii=False)}
    finally:
        await task
