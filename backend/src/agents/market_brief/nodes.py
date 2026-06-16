"""Individual loop steps — each independently testable (rules.md §A).

Nodes contain the pure mechanics (LLM call, tool dispatch, state mutations,
parsing helpers).  agent.py wires them into the while-loop; nodes never
import from agent.py.

Side-effect helpers (_post_tool_side_effects, _maybe_emit_anomaly_focus) are
best-effort: they MUST NOT propagate exceptions out of the loop.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any

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

_log = logging.getLogger("market_brief.nodes")

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


def _fixup_brief_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Lightweight fixup for common LLM output issues before strict validation.

    Groq / llama models sometimes omit the URL field on news/web citations.
    The schema requires url for kind != 'tool'.  Promote these to kind='tool'
    so the brief doesn't silently fail on the first parse attempt (requiring a
    costly repair round that may hit the provider's daily token cap).
    """
    citations = data.get("citations")
    if not isinstance(citations, list):
        return data
    fixed = []
    for c in citations:
        if isinstance(c, dict) and c.get("kind") in ("news", "web") and not c.get("url"):
            _log.warning(
                "[fixup] citation %r has kind=%r but null url — promoting to kind='tool'",
                c.get("id"),
                c.get("kind"),
            )
            c = {**c, "kind": "tool"}
        fixed.append(c)
    return {**data, "citations": fixed}


# Honest fallback when an anomaly's only support was an ungrounded citation.
_NO_CAUSE_EXPLANATION = "No public cause could be confirmed from the retrieved sources."


def _collect_urls(obj: Any) -> set[str]:
    """Recursively collect non-empty string values under any key named ``"url"``.

    Mirrors evals.checks.grounded_urls so the runtime grounding guard and the
    offline faithfulness metric agree on exactly what counts as "retrieved".
    """
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "url" and isinstance(value, str) and value:
                found.add(value)
            else:
                found |= _collect_urls(value)
    elif isinstance(obj, list):
        for item in obj:
            found |= _collect_urls(item)
    return found


def _enforce_citation_grounding(data: dict[str, Any], seen_urls: set[str]) -> dict[str, Any]:
    """Drop any news/web citation whose URL was never returned by a tool.

    rules.md: every claim is cited to a *real* tool result/URL, and "no clear
    public cause found" beats an invented explanation. A model can hallucinate a
    plausible-looking source URL; this STRENGTHENS the citation guarantee by
    removing such citations deterministically and repairing the references:
      * bullets left with only fabricated citations are dropped entirely;
      * an anomaly that loses all support falls back to low confidence with an
        honest "no public cause" explanation.
    """
    citations = data.get("citations")
    if not isinstance(citations, list):
        return data

    fabricated: set[Any] = set()
    kept: list[Any] = []
    for c in citations:
        if isinstance(c, dict) and c.get("kind") in ("news", "web"):
            url = c.get("url")
            if not url or url not in seen_urls:
                fabricated.add(c.get("id"))
                _log.warning(
                    "[grounding] dropping ungrounded %s citation %r (url=%r)",
                    c.get("kind"),
                    c.get("id"),
                    url,
                )
                continue
        kept.append(c)

    if not fabricated:
        return data

    data = {**data, "citations": kept}

    for key in ("news_highlights", "bull_case", "bear_case", "risks"):
        bullets = data.get(key)
        if not isinstance(bullets, list):
            continue
        new_bullets: list[Any] = []
        for b in bullets:
            if not isinstance(b, dict):
                new_bullets.append(b)
                continue
            cites = [cid for cid in b.get("citations", []) if cid not in fabricated]
            if not cites:
                _log.warning(
                    "[grounding] dropping %s bullet with only ungrounded citations: %r",
                    key,
                    str(b.get("text", ""))[:80],
                )
                continue
            new_bullets.append({**b, "citations": cites})
        data[key] = new_bullets

    anomalies = data.get("anomalies")
    if isinstance(anomalies, list):
        new_anoms: list[Any] = []
        for a in anomalies:
            if not isinstance(a, dict):
                new_anoms.append(a)
                continue
            original = a.get("citations", [])
            cites = [cid for cid in original if cid not in fabricated]
            if original and not cites:
                _log.warning(
                    "[grounding] anomaly %r lost all support → low confidence",
                    a.get("date"),
                )
                a = {
                    **a,
                    "citations": [],
                    "confidence": "low",
                    "explanation": _NO_CAUSE_EXPLANATION,
                }
            else:
                a = {**a, "citations": cites}
            new_anoms.append(a)
        data["anomalies"] = new_anoms

    return data


def parse_final(text: str, seen_urls: set[str] | None = None) -> MarketBrief:
    """Parse the LLM's final text as a MarketBrief.

    Applies lightweight fixups for known LLM formatting quirks before strict
    Pydantic validation; propagates ValidationError or ValueError on failure.

    When *seen_urls* is provided, news/web citations whose URL was not returned
    by any tool during the run are rejected as ungrounded (fabricated) before
    validation — see _enforce_citation_grounding.
    """
    raw = strip_code_fences(text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"brief is not valid JSON: {exc}") from exc
    if isinstance(data, dict):
        data = _fixup_brief_dict(data)
        if seen_urls is not None:
            data = _enforce_citation_grounding(data, seen_urls)
    return parse_brief(data)


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

    if state.price_history_out:
        ph = state.price_history_out
        for key in ("low_52w", "high_52w"):
            if ph.get(key) is not None:
                brief.snapshot[key] = ph[key]
        # Deterministically overwrite price/change fields (LLM must not own these)
        if ph.get("latest_close") is not None:
            brief.snapshot["price"] = ph["latest_close"]
        change_pct = ph.get("change_pct")
        if isinstance(change_pct, dict):
            if change_pct.get("d1") is not None:
                brief.snapshot["change_1d"] = change_pct["d1"]
            if change_pct.get("m1") is not None:
                brief.snapshot["change_1m"] = change_pct["m1"]
            if change_pct.get("period") is not None:
                brief.snapshot["change_period"] = change_pct["period"]
        if ph.get("currency") is not None:
            brief.snapshot["currency"] = ph["currency"]

    if state.fundamentals_out:
        fund = state.fundamentals_out
        if fund.get("market_cap") is not None:
            brief.snapshot["market_cap"] = fund["market_cap"]
        # prefer trailing P/E; fall back to forward
        pe = fund.get("pe_trailing")
        if pe is None:
            pe = fund.get("pe_forward")
        if pe is not None:
            brief.snapshot["pe"] = pe
        if fund.get("sector") is not None:
            brief.snapshot["sector"] = fund["sector"]


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
