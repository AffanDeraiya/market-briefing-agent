"""Eval metrics: citation faithfulness and structure compliance.

Both checks return a (score, failing_ids_or_names) tuple so callers can
report exactly what failed rather than only a number.
"""

from __future__ import annotations

import json
from typing import Any

from src.schemas import DISCLAIMER, MarketBrief

__all__ = [
    "FAITHFULNESS_GATE",
    "STRUCTURE_GATE",
    "grounded_urls",
    "citation_faithfulness",
    "structure_compliance",
]

# ---------------------------------------------------------------------------
# Gate thresholds
# ---------------------------------------------------------------------------

FAITHFULNESS_GATE: float = 0.95
STRUCTURE_GATE: float = 0.98


# ---------------------------------------------------------------------------
# URL extraction helpers
# ---------------------------------------------------------------------------


def _collect_urls(obj: Any) -> set[str]:
    """Recursively walk a JSON-decoded object and collect non-empty string
    values stored under a key literally named ``"url"``.
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


def grounded_urls(tool_io: list[dict[str, Any]]) -> set[str]:
    """Union of every URL found inside the recorded tool outputs.

    Each item's ``"output"`` field is a JSON string; malformed entries are
    silently skipped so a single bad record does not corrupt the whole set.
    """
    urls: set[str] = set()
    for item in tool_io:
        try:
            parsed: Any = json.loads(item["output"])
            urls |= _collect_urls(parsed)
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    return urls


# ---------------------------------------------------------------------------
# Metric 1 — Citation faithfulness
# ---------------------------------------------------------------------------


def citation_faithfulness(
    brief: MarketBrief,
    tool_io: list[dict[str, Any]],
) -> tuple[float, list[str]]:
    """Return (score, unfaithful_citation_ids).

    A citation is FAITHFUL when:
      * kind == "tool"  (these are internal references, never fabricated), OR
      * url is non-empty AND that url appears in at least one tool result.

    Rationale: a news/web citation whose URL never appeared in any tool result
    output was not retrieved during the run and was likely fabricated.

    Returns (1.0, []) when the brief has zero citations.
    """
    if not brief.citations:
        return 1.0, []

    ground = grounded_urls(tool_io)
    unfaithful: list[str] = []

    for citation in brief.citations:
        if citation.kind == "tool":
            continue  # always faithful
        if citation.url and citation.url in ground:
            continue  # URL found in tool output → faithful
        unfaithful.append(citation.id)

    total = len(brief.citations)
    faithful_count = total - len(unfaithful)
    score = faithful_count / total
    return score, unfaithful


# ---------------------------------------------------------------------------
# Metric 2 — Structure compliance
# ---------------------------------------------------------------------------


def structure_compliance(brief: MarketBrief) -> tuple[float, list[str]]:
    """Return (score, failed_check_names).

    Runs a fixed checklist of boolean assertions; score = passed / total.
    Returns (1.0, []) only when every check passes.

    Checks (in order):
      1. disclaimer_exact          — disclaimer matches DISCLAIMER constant exactly
      2. technical_summary_nonempty — technical_summary is a non-empty string
      3. caps_respected            — list-length caps from schema.md respected
      4. bullets_cited             — every Bullet in all four lists has >=1 citation
      5. anomalies_explained       — every Anomaly has a non-empty explanation
      6. snapshot_keys             — snapshot contains all five required keys
      7. indicators_present        — indicators dict is non-empty
      8. citations_resolve         — every citation id referenced anywhere is defined
    """
    defined_ids: set[str] = {c.id for c in brief.citations}

    # 1. disclaimer_exact
    check_disclaimer = brief.disclaimer == DISCLAIMER

    # 2. technical_summary_nonempty
    check_technical = bool(brief.technical_summary.strip())

    # 3. caps_respected — schema.md: <=5 news, <=4 bull/bear, <=3 risks
    check_caps = (
        len(brief.news_highlights) <= 5
        and len(brief.bull_case) <= 4
        and len(brief.bear_case) <= 4
        and len(brief.risks) <= 3
    )

    # 4. bullets_cited — every bullet in all four sections has >=1 citation id
    all_bullets = brief.news_highlights + brief.bull_case + brief.bear_case + brief.risks
    check_bullets_cited = all(len(b.citations) >= 1 for b in all_bullets)

    # 5. anomalies_explained — every anomaly has a non-empty explanation string
    check_anomalies_explained = all(bool(a.explanation.strip()) for a in brief.anomalies)

    # 6. snapshot_keys — must include these five keys
    required_snapshot_keys = {"price", "change_1d", "change_1m", "change_period", "sector"}
    check_snapshot_keys = required_snapshot_keys.issubset(brief.snapshot.keys())

    # 7. indicators_present — indicators dict must be non-empty
    check_indicators = bool(brief.indicators)

    # 8. citations_resolve — every id referenced in anomalies + bullets is defined
    referenced: set[str] = set()
    for anomaly in brief.anomalies:
        referenced.update(anomaly.citations)
    for bullet in all_bullets:
        referenced.update(bullet.citations)
    check_citations_resolve = referenced.issubset(defined_ids)

    checks: list[tuple[str, bool]] = [
        ("disclaimer_exact", check_disclaimer),
        ("technical_summary_nonempty", check_technical),
        ("caps_respected", check_caps),
        ("bullets_cited", check_bullets_cited),
        ("anomalies_explained", check_anomalies_explained),
        ("snapshot_keys", check_snapshot_keys),
        ("indicators_present", check_indicators),
        ("citations_resolve", check_citations_resolve),
    ]

    failed = [name for name, passed in checks if not passed]
    total = len(checks)
    score = (total - len(failed)) / total
    return score, failed
