"""Individual loop steps — each independently testable (rules.md §A).

Nodes contain the pure mechanics (LLM call, tool dispatch, state mutations,
parsing helpers).  agent.py wires them into the while-loop; nodes never
import from agent.py.

Side-effect helpers (_post_tool_side_effects, _maybe_emit_anomaly_focus) are
best-effort: they MUST NOT propagate exceptions out of the loop.
"""

from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING

from src.llm import LLMBackend, LLMResponse, ToolResult, ToolSpec, Turn
from src.schemas import MarketBrief, parse_brief

from .events import (
    EVENT_ANOMALY_FOCUS,
    EVENT_CHART_DATA,
    EVENT_TOOL_CALL,
    EVENT_TOOL_RESULT,
    Emitter,
)
from .prompts import FINALIZE_NOW_MESSAGE, build_repair_message
from .state import RunState
from .tools import execute_tool

if TYPE_CHECKING:
    from .cassette import CassetteRecorder

__all__ = [
    "call_llm",
    "run_tool_calls",
    "strip_code_fences",
    "parse_final",
    "attach_market_data",
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

        for d_str, kind in state.anomaly_dates.items():
            try:
                d = date.fromisoformat(d_str)
                if from_date <= d <= to_date:
                    emit(EVENT_ANOMALY_FOCUS, {"date": d_str, "kind": kind})
            except (ValueError, TypeError):
                pass
    except Exception:  # noqa: BLE001
        pass


def _post_tool_side_effects(
    state: RunState,
    tc_name: str,
    content: str,
    is_error: bool,
    emit: Emitter,
) -> None:
    """Apply state side effects and supplementary events after a tool returns."""
    try:
        if tc_name == "detect_anomalies" and not is_error:
            data = json.loads(content)
            for a in data.get("anomalies", []):
                d_str = a.get("date", "")
                kind = a.get("kind", "")
                if d_str and kind:
                    state.anomaly_dates[d_str] = kind
    except Exception:  # noqa: BLE001
        pass

    try:
        if tc_name == "get_price_history" and not is_error:
            anomalies_list = [{"date": d, "kind": k} for d, k in state.anomaly_dates.items()]
            emit(EVENT_CHART_DATA, {"ohlcv": [], "anomalies": anomalies_list})
    except Exception:  # noqa: BLE001
        pass

    # Capture structured tool outputs for deterministic brief enrichment.
    try:
        if tc_name == "compute_indicators" and not is_error:
            state.indicators_out = json.loads(content)
    except Exception:  # noqa: BLE001
        pass

    try:
        if tc_name == "get_fundamentals" and not is_error:
            state.fundamentals_out = json.loads(content)
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

        t0 = time.monotonic()
        content, is_error = execute_tool(tc.name, tc.input)
        ms = int((time.monotonic() - t0) * 1000)

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
# Parsing helpers
# ---------------------------------------------------------------------------

_CODE_FENCE_RE = re.compile(
    r"^```(?:json)?\s*\n(.*?)\n```\s*$",
    re.DOTALL,
)


def strip_code_fences(text: str) -> str:
    """Remove a leading ```json / ``` fence and trailing ``` if present.

    Returns the inner content stripped of surrounding whitespace.
    """
    stripped = text.strip()
    m = _CODE_FENCE_RE.match(stripped)
    if m:
        return m.group(1).strip()
    return stripped


def parse_final(text: str) -> MarketBrief:
    """Parse the LLM's final text as a MarketBrief.

    Propagates pydantic.ValidationError or ValueError on failure.
    """
    return parse_brief(strip_code_fences(text))


def attach_market_data(state: RunState, brief: MarketBrief) -> None:
    """Overwrite the brief's numeric indicator / 52-week fields with the
    authoritative tool outputs captured during the run.

    Rules.md: the LLM never owns these numbers. Best-effort — if a tool was not
    called (e.g. in unit tests), the corresponding fields are left untouched.
    """
    if state.indicators_out:
        ind = state.indicators_out
        mdd = ind.get("max_drawdown_pct")
        brief.indicators = {
            "rsi14": ind.get("rsi14"),
            "rsi_signal": ind.get("rsi_signal"),
            "annualized_vol_pct": ind.get("annualized_vol_pct"),
            # flatten the MaxDrawdown object to its percent value for the chips
            "max_drawdown_pct": mdd.get("value") if isinstance(mdd, dict) else mdd,
            "sma20_vs_price": ind.get("sma20_vs_price"),
            "sma50_vs_price": ind.get("sma50_vs_price"),
            "volume_trend": ind.get("volume_trend"),
        }

    if state.fundamentals_out:
        f = state.fundamentals_out
        for key in ("low_52w", "high_52w"):
            if f.get(key) is not None:
                brief.snapshot[key] = f[key]


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
