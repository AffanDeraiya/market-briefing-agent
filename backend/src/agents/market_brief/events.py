"""Event emission abstraction for the agent loop.

The loop emits events via an Emitter callable; consumers decide how to handle
them (stdout, SSE queue, test collector, etc.).

Event type constants defined here are the single source of truth — import them
rather than using raw strings.
"""

from __future__ import annotations

import contextlib
import json
import sys
from collections.abc import Callable
from typing import Any

__all__ = [
    "Emitter",
    "EVENT_RUN_STARTED",
    "EVENT_STEP",
    "EVENT_TOOL_CALL",
    "EVENT_TOOL_RESULT",
    "EVENT_CHART_DATA",
    "EVENT_ANOMALY_FOCUS",
    "EVENT_BRIEF",
    "EVENT_VERIFY_STARTED",
    "EVENT_CLAIM_VERDICT",
    "EVENT_VERIFY_DONE",
    "EVENT_USAGE",
    "EVENT_ERROR",
    "noop_emitter",
    "make_stdout_emitter",
    "CollectingEmitter",
    "estimate_cost_usd",
]

# ---------------------------------------------------------------------------
# Emitter type alias
# ---------------------------------------------------------------------------

Emitter = Callable[[str, dict[str, Any]], None]  # (event_type, data)

# ---------------------------------------------------------------------------
# Event type string constants
# ---------------------------------------------------------------------------

EVENT_RUN_STARTED = "run_started"
EVENT_STEP = "step"
EVENT_TOOL_CALL = "tool_call"
EVENT_TOOL_RESULT = "tool_result"
EVENT_CHART_DATA = "chart_data"
EVENT_ANOMALY_FOCUS = "anomaly_focus"
EVENT_BRIEF = "brief"
# Claim Verifier events (L2 live before→after revision)
EVENT_VERIFY_STARTED = "verify_started"
EVENT_CLAIM_VERDICT = "claim_verdict"
EVENT_VERIFY_DONE = "verify_done"
EVENT_USAGE = "usage"
EVENT_ERROR = "error"

# ---------------------------------------------------------------------------
# Noop emitter
# ---------------------------------------------------------------------------


def noop_emitter(event_type: str, data: dict[str, Any]) -> None:
    """Silently discard every event — use as the default in non-interactive contexts."""


# ---------------------------------------------------------------------------
# Stdout emitter factory
# ---------------------------------------------------------------------------

_TRUNCATE_AT = 200


def _truncate(s: str, n: int = _TRUNCATE_AT) -> str:
    return s if len(s) <= n else s[:n] + "…"


def _fmt(data: dict[str, Any]) -> str:
    """Render event data as a compact one-line string."""
    try:
        return _truncate(json.dumps(data, ensure_ascii=False))
    except (TypeError, ValueError):
        return _truncate(str(data))


def make_stdout_emitter() -> Emitter:
    """Return an Emitter that prints a concise one-line summary per event.

    Windows consoles default to cp1252; agent output legitimately contains
    non-cp1252 characters (e.g. the σ in "-3.6σ", arrows). Make stdout tolerant
    so a console-encoding error can never propagate up and abort an agent run.
    """
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[union-attr]

    def _emit(event_type: str, data: dict[str, Any]) -> None:
        if event_type == EVENT_TOOL_CALL:
            seq = data.get("seq", "?")
            name = data.get("name", "?")
            inp = data.get("input", {})
            print(f"[tool_call #{seq}] {name} {_truncate(json.dumps(inp, ensure_ascii=False))}")

        elif event_type == EVENT_TOOL_RESULT:
            seq = data.get("seq", "?")
            name = data.get("name", "?")
            ok = data.get("ok", False)
            ms = data.get("ms", "?")
            summary = _truncate(str(data.get("summary", "")), 120)
            print(f"[tool_result #{seq}] {name} ok={ok} {ms}ms  {summary}")

        elif event_type == EVENT_STEP:
            it = data.get("iteration", "?")
            thinking = _truncate(str(data.get("thinking", "")), 160)
            print(f"[step it={it}] {thinking}")

        elif event_type == EVENT_RUN_STARTED:
            ticker = data.get("ticker", "?")
            model = data.get("model", "?")
            period = data.get("period", "?")
            run_id = data.get("run_id", "?")
            print(f"[run_started] ticker={ticker} model={model} period={period} run_id={run_id}")

        elif event_type == EVENT_BRIEF:
            print(f"[brief] {json.dumps(data, indent=2, ensure_ascii=False)}")

        elif event_type == EVENT_USAGE:
            print(f"[usage] {_fmt(data)}")

        elif event_type == EVENT_ERROR:
            kind = data.get("kind", "?")
            msg = _truncate(str(data.get("message", "")), 200)
            print(f"[error] kind={kind} {msg}")

        elif event_type == EVENT_ANOMALY_FOCUS:
            d = data.get("date", "?")
            kind = data.get("kind", "?")
            print(f"[anomaly_focus] date={d} kind={kind}")

        elif event_type == EVENT_CHART_DATA:
            anomalies = data.get("anomalies", [])
            print(f"[chart_data] anomalies={len(anomalies)}")

        else:
            print(f"[{event_type}] {_fmt(data)}")

    return _emit


# ---------------------------------------------------------------------------
# Collecting emitter (for tests / cassette replay)
# ---------------------------------------------------------------------------


class CollectingEmitter:
    """Records (event_type, data) tuples for tests and offline replay."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, event_type: str, data: dict[str, Any]) -> None:
        self.events.append((event_type, data))

    def types(self) -> list[str]:
        return [e[0] for e in self.events]


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

# Approximate pricing per 1 M tokens (USD) as of 2024-12-01.
# Gemini free tier is priced at $0; all other models default to 0.0 unless listed.
_PRICE_TABLE: dict[str, tuple[float, float]] = {
    # model-id → (input $/1M, output $/1M)
    "claude-haiku-4-5": (1.00, 5.00),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate the USD cost for a completed run.

    Pricing is approximate and subject to change.  Returns 0.0 for models not
    in the price table (e.g. Gemini free tier).
    """
    if model not in _PRICE_TABLE:
        return 0.0
    input_price, output_price = _PRICE_TABLE[model]
    cost = (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
    return round(cost, 6)
