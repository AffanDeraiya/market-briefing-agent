"""Brief parsing, citation-grounding, and deterministic market-data enrichment.

Helpers extracted from nodes.py so the node module holds only the LangGraph node
definitions.  Pure mechanics: no graph/config awareness.

- strip_code_fences / _fixup_brief_dict  — normalize raw LLM output
- _collect_urls / _enforce_citation_grounding — drop ungrounded (fabricated)
  news/web citations (mirrors evals.checks.grounded_urls)
- parse_final — strip → fixup → ground → strict Pydantic validation
- attach_market_data — overwrite numeric fields with authoritative tool outputs
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.schemas import MarketBrief, parse_brief

from ..state import RunState

_log = logging.getLogger("market_brief.parsing")

__all__ = [
    "strip_code_fences",
    "parse_final",
    "attach_market_data",
]


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

# Honest fallback when a signal's only support was ungrounded citations.
_NO_SIGNAL_RATIONALE = "Insufficient grounded evidence for a directional call."


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

    signal = data.get("signal")
    if isinstance(signal, dict):
        original = signal.get("citations", [])
        cites = [cid for cid in original if cid not in fabricated]
        if original and not cites:
            _log.warning("[grounding] signal lost all support → neutral/low")
            signal = {
                **signal,
                "stance": "neutral",
                "confidence": "low",
                "citations": [],
                "rationale": _NO_SIGNAL_RATIONALE,
            }
        else:
            signal = {**signal, "citations": cites}
        data["signal"] = signal

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
    # The LLM never authors dates — stamp the signal's as_of from the brief's.
    if brief.signal is not None:
        brief.signal.as_of = brief.as_of

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
