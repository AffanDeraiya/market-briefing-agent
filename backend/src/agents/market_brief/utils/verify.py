"""Claim Verifier logic for the Market Briefing Agent.

Public surface
--------------
count_claims(brief)              → int
run_verification(brief, run, *, backend, verify_llm) → Verification | None

The verifier audits the brief's cited claims against the evidence retrieved
during the run (run.history), mutates the brief in place where appropriate
(downgrade confidence / drop claim / neutralize signal), and returns a
Verification summary.  If nothing is actionable (no verdicts), returns None.

Deterministic layer (§D.1 of the spec): always runs; conservative — must NOT
fire on valid/clean cassette briefs.  Currently only checks signal consistency:
a bullish/accumulate stance with zero bull_case items is contradictory.

LLM semantic layer (§D.2): runs only when verify_llm=True and a backend is
provided.  Any exception is caught and logged; the run always continues.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from src.llm import LLMBackend, Turn
from src.schemas import ClaimVerdict, MarketBrief, Verification

from ..prompts import VERIFIER_SYSTEM_PROMPT, build_verifier_message
from ..state import RunState

if TYPE_CHECKING:
    pass  # no additional TYPE_CHECKING imports needed

__all__ = ["count_claims", "run_verification"]

_log = logging.getLogger("market_brief.verify")

# Maximum total characters we include in the evidence block so the verifier
# prompt stays bounded (rules.md: every external call is bounded).
_MAX_EVIDENCE_CHARS = 6000

# Confidence downgrade order
_CONFIDENCE_DOWNGRADE: dict[str, str] = {
    "high": "medium",
    "medium": "low",
    "low": "low",
}

# Honest fallback text used when we neutralize an anomaly
_NO_CAUSE_EXPLANATION = "No public cause could be confirmed from the retrieved sources."

# Honest fallback rationale used when we neutralize a signal
_NO_SIGNAL_RATIONALE = "Insufficient grounded evidence for a directional call."

# Regex for stripping markdown code fences from LLM output
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


# ---------------------------------------------------------------------------
# count_claims
# ---------------------------------------------------------------------------


def count_claims(brief: MarketBrief) -> int:
    """Return the number of auditable cited claims in *brief*.

    Counts:
    - every bullet in news_highlights, bull_case, bear_case, risks
    - each anomaly whose citations list is non-empty
    - 1 if brief.signal is not None and stance is not "neutral"
    """
    count = 0
    for bullet_list in (
        brief.news_highlights,
        brief.bull_case,
        brief.bear_case,
        brief.risks,
    ):
        count += len(bullet_list)

    for anomaly in brief.anomalies:
        if anomaly.citations:
            count += 1

    if brief.signal is not None and brief.signal.stance != "neutral":
        count += 1

    return count


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _truncate(text: str, max_chars: int = 80) -> str:
    """Truncate *text* to *max_chars*, appending '…' if needed."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _build_claims_block(brief: MarketBrief) -> list[tuple[str, str, str]]:
    """Return a list of (target_id, label, claim_text) for every auditable claim.

    target_id follows the convention documented in the spec:
        "news_highlights:<index>"  "bull_case:<index>"  "bear_case:<index>"
        "risks:<index>"            "anomaly:<YYYY-MM-DD>"  "signal"
    """
    items: list[tuple[str, str, str]] = []

    sections: list[tuple[str, Any]] = [
        ("news_highlights", brief.news_highlights),
        ("bull_case", brief.bull_case),
        ("bear_case", brief.bear_case),
        ("risks", brief.risks),
    ]
    for section_name, bullets in sections:
        for idx, bullet in enumerate(bullets):
            target = f"{section_name}:{idx}"
            items.append((target, _truncate(bullet.text), bullet.text))

    for anomaly in brief.anomalies:
        if anomaly.citations:
            target = f"anomaly:{anomaly.date}"
            label = f"{anomaly.date} {anomaly.kind}: {anomaly.magnitude}"
            items.append((target, _truncate(label), anomaly.explanation))

    if brief.signal is not None and brief.signal.stance != "neutral":
        label = f"signal({brief.signal.stance}): {_truncate(brief.signal.rationale)}"
        items.append(("signal", label, brief.signal.rationale))

    return items


def _build_claims_text(
    brief: MarketBrief,
    claims: list[tuple[str, str, str]],
) -> str:
    """Render the claims block string sent to the verifier prompt.

    Each line: "<target> | <label> | cited_sources: <titles/urls>"
    Citation titles + URLs are looked up from brief.citations.
    """
    cit_map = {c.id: c for c in brief.citations}
    lines: list[str] = []
    for target, label, _ in claims:
        # Determine which citation ids belong to this claim
        cit_ids: list[str] = []
        if target.startswith("news_highlights:"):
            idx = int(target.split(":")[1])
            cit_ids = brief.news_highlights[idx].citations
        elif target.startswith("bull_case:"):
            idx = int(target.split(":")[1])
            cit_ids = brief.bull_case[idx].citations
        elif target.startswith("bear_case:"):
            idx = int(target.split(":")[1])
            cit_ids = brief.bear_case[idx].citations
        elif target.startswith("risks:"):
            idx = int(target.split(":")[1])
            cit_ids = brief.risks[idx].citations
        elif target.startswith("anomaly:"):
            date_str = target[len("anomaly:") :]
            for a in brief.anomalies:
                if a.date == date_str:
                    cit_ids = a.citations
                    break
        elif target == "signal" and brief.signal is not None:
            cit_ids = brief.signal.citations

        sources_parts: list[str] = []
        for cid in cit_ids:
            cit = cit_map.get(cid)
            if cit is None:
                continue
            if cit.url:
                sources_parts.append(f"{cit.title} ({cit.url})")
            else:
                sources_parts.append(cit.title)
        sources_str = "; ".join(sources_parts) if sources_parts else "(no sources)"
        lines.append(f"[{target}] {label} | sources: {sources_str}")

    return "\n".join(lines)


def _build_evidence_text(brief: MarketBrief, run: RunState) -> str:
    """Build the evidence block from run.history tool-result turns and brief.citations.

    Tool results are carried in turns with role == "tool" (each has .tool_results
    list with .content text).  We also include all assistant text turns after the
    initial user turn as context, bounded to _MAX_EVIDENCE_CHARS total.
    """
    parts: list[str] = []

    # Gather tool-result content from history
    for turn in run.history:
        if turn.role == "tool":
            for tr in turn.tool_results:
                if tr.content.strip():
                    parts.append(f"[tool:{tr.name}] {tr.content[:1000]}")

    # Include citation list from the brief itself as a supplement
    cit_lines: list[str] = []
    for c in brief.citations:
        if c.url:
            cit_lines.append(f"  {c.id}: {c.kind} | {c.title} | {c.url}")
        else:
            cit_lines.append(f"  {c.id}: {c.kind} | {c.title}")
    if cit_lines:
        parts.append("BRIEF CITATIONS:\n" + "\n".join(cit_lines))

    evidence = "\n\n".join(parts)
    # Truncate to the cap
    if len(evidence) > _MAX_EVIDENCE_CHARS:
        evidence = evidence[:_MAX_EVIDENCE_CHARS] + "\n...[truncated]"
    return evidence


def _strip_fences(text: str) -> str:
    """Remove ``` or ```json code fences defensively."""
    stripped = text.strip()
    m = _CODE_FENCE_RE.match(stripped)
    if m:
        return m.group(1).strip()
    return stripped


# ---------------------------------------------------------------------------
# Mutation helpers — constraint-preserving
# ---------------------------------------------------------------------------


def _neutralize_anomaly(anomaly: Any) -> None:
    """Neutralize an anomaly in place: low confidence, clear citations, honest explanation."""
    anomaly.confidence = "low"
    anomaly.citations = []
    anomaly.explanation = _NO_CAUSE_EXPLANATION


def _neutralize_signal(signal: Any) -> None:
    """Neutralize the signal in place: neutral stance, low confidence, clear citations."""
    signal.stance = "neutral"
    signal.confidence = "low"
    signal.citations = []
    signal.rationale = _NO_SIGNAL_RATIONALE


def _downgrade_confidence(obj: Any) -> tuple[str, bool]:
    """Downgrade obj.confidence one notch.  Returns (new_value, actually_changed)."""
    old = obj.confidence
    new = _CONFIDENCE_DOWNGRADE.get(old, "low")
    obj.confidence = new
    return new, old != new


# ---------------------------------------------------------------------------
# Deterministic layer
# ---------------------------------------------------------------------------


def _run_deterministic(brief: MarketBrief) -> list[ClaimVerdict]:
    """Run purely deterministic consistency checks.  MUST be conservative —
    must NOT fire on valid/clean cassette briefs.

    Current checks:
    1. Signal consistency: buy/accumulate stance with zero bull_case items.
    """
    verdicts: list[ClaimVerdict] = []

    if (
        brief.signal is not None
        and brief.signal.stance in {"buy", "accumulate"}
        and len(brief.bull_case) == 0
    ):
        _log.warning(
            "[verify:det] signal stance=%r with empty bull_case → neutralizing",
            brief.signal.stance,
        )
        note = (
            f"Signal stance '{brief.signal.stance}' is inconsistent with "
            "zero bull-case items — no supporting evidence for a bullish call."
        )
        _neutralize_signal(brief.signal)
        verdicts.append(
            ClaimVerdict(
                target="signal",
                label=f"signal({brief.signal.stance})",
                verdict="unsupported",
                action="neutralized",
                note=note,
            )
        )

    return verdicts


# ---------------------------------------------------------------------------
# LLM semantic layer
# ---------------------------------------------------------------------------


def _run_llm_layer(
    brief: MarketBrief,
    run: RunState,
    backend: LLMBackend,
    claims: list[tuple[str, str, str]],
) -> list[ClaimVerdict]:
    """Run the LLM semantic verification layer.  Returns verdicts or raises."""
    claims_text = _build_claims_text(brief, claims)
    evidence_text = _build_evidence_text(brief, run)
    user_msg = build_verifier_message(claims_text, evidence_text)

    resp = backend.complete(
        system=VERIFIER_SYSTEM_PROMPT,
        history=[Turn(role="user", text=user_msg)],
        tools=[],
        max_tokens=1024,
    )

    # Count tokens into the run (verifier cost attribution)
    run.input_tokens += resp.usage.input_tokens
    run.output_tokens += resp.usage.output_tokens

    # Parse the LLM's JSON response
    raw = _strip_fences(resp.text)
    data = json.loads(raw)  # raises json.JSONDecodeError on malformed
    raw_verdicts = data.get("verdicts")
    if not isinstance(raw_verdicts, list):
        raise ValueError(f"expected 'verdicts' list, got {type(raw_verdicts)}")

    # Build a lookup of valid targets
    valid_targets = {target for target, _, _ in claims}

    # Build a label map: target → label
    label_map = {target: label for target, label, _ in claims}

    llm_verdicts: list[ClaimVerdict] = []

    for item in raw_verdicts:
        if not isinstance(item, dict):
            continue
        target = item.get("target", "")
        verdict_str = item.get("verdict", "")
        note = str(item.get("note", ""))

        if target not in valid_targets:
            _log.debug("[verify:llm] ignoring unknown target %r", target)
            continue
        if verdict_str not in {"supported", "partial", "unsupported"}:
            _log.debug("[verify:llm] ignoring invalid verdict %r for %r", verdict_str, target)
            continue

        label: str = label_map.get(target) or target
        action, claim_verdict = _apply_llm_verdict(brief, target, verdict_str, note)
        llm_verdicts.append(
            ClaimVerdict(
                target=target,
                label=_truncate(label),
                verdict=claim_verdict,  # type: ignore[arg-type]
                action=action,  # type: ignore[arg-type]
                note=note,
            )
        )

    return llm_verdicts


def _apply_llm_verdict(
    brief: MarketBrief,
    target: str,
    verdict_str: str,
    note: str,
) -> tuple[str, str]:
    """Mutate the brief based on the LLM verdict.  Returns (action, verdict)."""
    verdict: str = verdict_str

    if verdict_str == "supported":
        return ("kept", verdict)

    # Determine target type
    is_anomaly = target.startswith("anomaly:")
    is_signal = target == "signal"
    is_bullet = not is_anomaly and not is_signal

    if verdict_str == "partial":
        if is_anomaly:
            date_str = target[len("anomaly:") :]
            for anomaly in brief.anomalies:
                if anomaly.date == date_str:
                    _, changed = _downgrade_confidence(anomaly)
                    action = "confidence_downgraded" if changed else "kept"
                    return (action, verdict)
            return ("kept", verdict)

        if is_signal and brief.signal is not None:
            _, changed = _downgrade_confidence(brief.signal)
            action = "confidence_downgraded" if changed else "kept"
            return (action, verdict)

        # bullet: no confidence field, just note it
        return ("kept", verdict)

    # unsupported
    if is_anomaly:
        date_str = target[len("anomaly:") :]
        for anomaly in brief.anomalies:
            if anomaly.date == date_str:
                _neutralize_anomaly(anomaly)
                return ("neutralized", verdict)
        return ("kept", verdict)

    if is_signal and brief.signal is not None:
        _neutralize_signal(brief.signal)
        return ("neutralized", verdict)

    if is_bullet:
        # Drop the bullet from its list
        _drop_bullet(brief, target)
        return ("dropped", verdict)

    return ("kept", verdict)


def _drop_bullet(brief: MarketBrief, target: str) -> None:
    """Remove the bullet identified by *target* from the appropriate list."""
    if ":" not in target:
        return
    section, idx_str = target.split(":", 1)
    try:
        idx = int(idx_str)
    except ValueError:
        return

    section_map: dict[str, list[Any]] = {
        "news_highlights": brief.news_highlights,
        "bull_case": brief.bull_case,
        "bear_case": brief.bear_case,
        "risks": brief.risks,
    }
    bullet_list = section_map.get(section)
    if bullet_list is None:
        return
    if 0 <= idx < len(bullet_list):
        _log.info("[verify:llm] dropping %s[%d]: %r", section, idx, bullet_list[idx].text[:80])
        bullet_list.pop(idx)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_verification(
    brief: MarketBrief,
    run: RunState,
    *,
    backend: LLMBackend | None,
    verify_llm: bool,
) -> Verification | None:
    """Audit the brief's cited claims against retrieved evidence.

    Mutates *brief* in place (downgrade confidence / drop / neutralize).
    Returns a Verification summary, or None if there is nothing to report.

    Parameters
    ----------
    brief:       The parsed MarketBrief to audit.
    run:         The RunState carrying run.history (tool-result turns) and token counts.
    backend:     The LLMBackend to use for the semantic layer (may be None).
    verify_llm:  If False, only the fast deterministic layer runs (eval/replay path).
    """
    # --- 1. Deterministic layer (always) ---
    det_verdicts = _run_deterministic(brief)

    # --- 2. LLM semantic layer (opt-in) ---
    llm_verdicts: list[ClaimVerdict] = []
    if verify_llm and backend is not None:
        claims = _build_claims_block(brief)
        if claims:
            try:
                llm_verdicts = _run_llm_layer(brief, run, backend, claims)
            except Exception:  # noqa: BLE001
                _log.warning(
                    "[verify:llm] LLM layer failed — falling back to deterministic only",
                    exc_info=True,
                )

    # --- 3. Combine & summarise ---
    all_verdicts = det_verdicts + llm_verdicts
    if not all_verdicts:
        return None

    checked = len(all_verdicts)
    supported = sum(1 for v in all_verdicts if v.verdict == "supported")
    adjusted = sum(1 for v in all_verdicts if v.action in {"confidence_downgraded", "neutralized"})
    dropped = sum(1 for v in all_verdicts if v.action == "dropped")

    result = Verification(
        verdicts=all_verdicts,
        checked=checked,
        supported=supported,
        adjusted=adjusted,
        dropped=dropped,
    )
    brief.verification = result
    return result
