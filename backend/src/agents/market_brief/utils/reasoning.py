"""LLM↔tool reasoning-loop mechanics.

Helpers extracted from nodes.py so the node module holds only the LangGraph node
definitions.  These are the pure mechanics the ``reason`` node drives: one LLM
call, the tool-execution loop, the post-tool side effects (state capture +
supplementary SSE events), and the finalize/repair turn injectors.

Side-effect helpers (_post_tool_side_effects, _maybe_emit_anomaly_focus) are
best-effort: they MUST NOT propagate exceptions out of the loop.

NB: ``execute_tool`` is imported here, so tests and the eval replay harness patch
``...utils.reasoning.execute_tool`` (not nodes.execute_tool) to stub tool I/O.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from src.llm import LLMBackend, LLMResponse, ToolResult, ToolSpec, Turn

from ..events import (
    EVENT_ANOMALY_FOCUS,
    EVENT_CHART_DATA,
    EVENT_TOOL_CALL,
    EVENT_TOOL_RESULT,
    Emitter,
)
from ..prompts import FINALIZE_NOW_MESSAGE, build_repair_message
from ..state import RunState
from ..tools import execute_tool
from .parsing import _collect_urls

if TYPE_CHECKING:
    from ..cassette import CassetteRecorder

_log = logging.getLogger("market_brief.reasoning")

__all__ = [
    "call_llm",
    "run_tool_calls",
    "inject_finalize",
    "inject_repair",
]


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------


def call_llm(
    state: RunState,
    backend: LLMBackend,
    *,
    system: str,
    tools: list[ToolSpec],
    max_tokens: int,
) -> LLMResponse:
    """Call the backend, update counters, append the assistant turn."""
    resp = backend.complete(
        system=system,
        history=state.history,
        tools=tools,
        max_tokens=max_tokens,
    )
    state.iterations += 1
    state.input_tokens += resp.usage.input_tokens
    state.output_tokens += resp.usage.output_tokens
    state.history.append(Turn(role="assistant", text=resp.text, tool_calls=resp.tool_calls))
    return resp


# ---------------------------------------------------------------------------
# Side-effect helpers (best-effort — never raise out of the loop)
# ---------------------------------------------------------------------------


def _maybe_emit_anomaly_focus(
    state: RunState,
    tc: ToolResult | object,  # actually a ToolCall from response.tool_calls
    emit: Emitter,
) -> None:
    """If calling get_company_news with a date window, emit anomaly_focus for
    each known anomaly date that falls within [from_date, to_date]."""
    try:
        from src.llm import ToolCall  # local import to keep module top clean

        if not isinstance(tc, ToolCall):
            return
        if tc.name != "get_company_news":
            return
        from_raw = tc.input.get("from_date") or ""
        to_raw = tc.input.get("to_date") or ""
        if not from_raw or not to_raw:
            return

        from datetime import date

        from_date = date.fromisoformat(from_raw.strip())
        to_date = date.fromisoformat(to_raw.strip())

        # Build a lookup from anomalies_detail for enriched payload
        detail_by_date: dict[str, dict[str, Any]] = {
            det["date"]: det for det in state.anomalies_detail if "date" in det
        }

        for d_str, kind in state.anomaly_dates.items():
            try:
                d = date.fromisoformat(d_str)
                if from_date <= d <= to_date:
                    detail = detail_by_date.get(d_str, {})
                    payload: dict[str, Any] = {"date": d_str, "kind": kind}
                    for field in ("magnitude", "sigma", "severity"):
                        if field in detail:
                            payload[field] = detail[field]
                    emit(EVENT_ANOMALY_FOCUS, payload)
            except (ValueError, TypeError):
                pass
    except Exception:  # noqa: BLE001
        pass


def _weekly_ohlcv(price_hist: dict[str, object]) -> list[dict[str, object]]:
    """Build the chart's weekly OHLCV series from a get_price_history output.

    The compact price-history payload only carries weekly close + volume, which is
    all the close-line chart consumes; open/high/low are set equal to close so the
    OHLCVPoint shape (schema.md / frontend types) is satisfied without inventing
    candle ranges.  Pure transform over the recorded tool output — replay-safe.
    """
    weeks = price_hist.get("week_aggregates")
    if not isinstance(weeks, list):
        return []
    ohlcv: list[dict[str, object]] = []
    for w in weeks:
        if not isinstance(w, dict):
            continue
        date_ = w.get("week_start")
        close = w.get("close")
        volume = w.get("volume")
        if date_ is None or close is None:
            continue
        ohlcv.append(
            {
                "date": date_,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": volume if volume is not None else 0,
            }
        )
    return ohlcv


def _post_tool_side_effects(
    state: RunState,
    tc_name: str,
    content: str,
    is_error: bool,
    emit: Emitter,
) -> None:
    """Apply state side effects and supplementary events after a tool returns."""
    # Record every URL this tool surfaced so the finalizer can reject any
    # news/web citation that was never actually retrieved (mirrors the eval's
    # grounded_urls). Applies to all tools; search/fetch_page are the sources.
    if not is_error:
        with contextlib.suppress(Exception):
            state.seen_urls |= _collect_urls(json.loads(content))

    try:
        if tc_name == "detect_anomalies" and not is_error:
            data = json.loads(content)
            for a in data.get("anomalies", []):
                d_str = a.get("date", "")
                kind = a.get("kind", "")
                if d_str and kind:
                    state.anomaly_dates[d_str] = kind
                # Store full anomaly detail (date, kind, magnitude, severity)
                detail: dict[str, Any] = {}
                for field in ("date", "kind", "magnitude", "severity"):
                    if field in a:
                        detail[field] = a[field]
                if detail.get("date") and detail.get("kind"):
                    state.anomalies_detail.append(detail)
            # Re-emit chart_data with full anomaly objects now that we have them.
            # If price history hasn't been captured yet, skip gracefully.
            if state.price_history_out:
                try:
                    ohlcv = _weekly_ohlcv(state.price_history_out)
                    anomalies_list = [
                        {
                            "date": d.get("date", ""),
                            "kind": d.get("kind", ""),
                            "magnitude": d.get("magnitude"),
                            "severity": d.get("severity"),
                        }
                        for d in state.anomalies_detail
                    ]
                    emit(EVENT_CHART_DATA, {"ohlcv": ohlcv, "anomalies": anomalies_list})
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass

    # Capture structured tool outputs for deterministic brief enrichment.
    # 52-week low/high come from get_price_history; indicators from compute_indicators.
    # Also emit the weekly price series for the chart early (anomalies list will be
    # empty here; a second emit with full anomaly objects follows after detect_anomalies).
    try:
        if tc_name == "get_price_history" and not is_error:
            price_hist = json.loads(content)
            state.price_history_out = price_hist
            ohlcv = _weekly_ohlcv(price_hist)
            emit(EVENT_CHART_DATA, {"ohlcv": ohlcv, "anomalies": []})
    except Exception:  # noqa: BLE001
        pass

    try:
        if tc_name == "get_fundamentals" and not is_error:
            state.fundamentals_out = json.loads(content)
    except Exception:  # noqa: BLE001
        pass

    try:
        if tc_name == "compute_indicators" and not is_error:
            state.indicators_out = json.loads(content)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Tool execution loop
# ---------------------------------------------------------------------------


def run_tool_calls(
    state: RunState,
    response: LLMResponse,
    emit: Emitter,
    *,
    recorder: CassetteRecorder | None = None,
) -> None:
    """Execute all tool calls in *response*, update state, append tool Turn."""
    results: list[ToolResult] = []

    for tc in response.tool_calls:
        seq = state.tool_calls_made + 1
        emit(EVENT_TOOL_CALL, {"seq": seq, "name": tc.name, "input": tc.input})
        _maybe_emit_anomaly_focus(state, tc, emit)

        input_summary = json.dumps(tc.input, ensure_ascii=False)[:200]
        _log.info("[tool_call #%d] %s | input=%s", seq, tc.name, input_summary)

        t0 = time.monotonic()
        content, is_error = execute_tool(tc.name, tc.input)
        ms = int((time.monotonic() - t0) * 1000)

        _log.info(
            "[tool_result #%d] %s | ok=%s ms=%d | %s", seq, tc.name, not is_error, ms, content[:200]
        )
        if is_error:
            _log.warning("[tool_error #%d] %s: %s", seq, tc.name, content[:400])

        emit(
            EVENT_TOOL_RESULT,
            {
                "seq": seq,
                "name": tc.name,
                "ok": not is_error,
                "summary": content[:200],
                "ms": ms,
            },
        )
        if recorder is not None:
            recorder.record_tool(seq, tc.name, tc.input, content)

        results.append(
            ToolResult(
                call_id=tc.id,
                name=tc.name,
                content=content,
                is_error=is_error,
            )
        )
        state.tool_calls_made += 1
        _post_tool_side_effects(state, tc.name, content, is_error, emit)

    state.history.append(Turn(role="tool", tool_results=results))


# ---------------------------------------------------------------------------
# State-mutation helpers
# ---------------------------------------------------------------------------


def inject_finalize(state: RunState) -> None:
    """Append the FINALIZE_NOW_MESSAGE user turn and mark it injected."""
    state.history.append(Turn(role="user", text=FINALIZE_NOW_MESSAGE))
    state.finalize_injected = True


def inject_repair(state: RunState, error: str) -> None:
    """Append a repair prompt user turn and mark repair as attempted."""
    state.history.append(Turn(role="user", text=build_repair_message(error)))
    state.repair_attempted = True
