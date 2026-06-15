"""Tests for the citation-grounding guard in parse_final.

rules.md: every claim is cited to a *real* tool result/URL. A model can
hallucinate a plausible-looking source URL; parse_final(text, seen_urls) must
deterministically drop such ungrounded news/web citations and repair the
references before strict validation.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from src.agents.market_brief.nodes import parse_final
from src.schemas import DISCLAIMER

_BRIEF: dict[str, Any] = {
    "ticker": "AAPL",
    "name": "Apple Inc.",
    "as_of": "2024-01-15",
    "period": "6mo",
    "snapshot": {
        "price": 185.50,
        "change_1d": 1.2,
        "change_1m": 3.4,
        "change_period": 8.1,
        "sector": "Technology",
    },
    "technical_summary": "Uptrend, RSI neutral.",
    "anomalies": [
        {
            "date": "2024-01-10",
            "kind": "price_spike",
            "magnitude": "+5.2% (3.1σ)",
            "explanation": "Earnings beat expectations.",
            "confidence": "high",
            "citations": ["c_news"],
        }
    ],
    "news_highlights": [{"text": "Apple reports record revenue.", "citations": ["c_news"]}],
    "bull_case": [{"text": "Strong iPhone cycle ahead.", "citations": ["c_tool"]}],
    "bear_case": [{"text": "Macro headwinds.", "citations": ["c_tool"]}],
    "risks": [{"text": "Regulatory scrutiny.", "citations": ["c_tool"]}],
    "citations": [
        {"id": "c_news", "url": "https://news.example.com/a", "title": "News", "kind": "news"},
        {"id": "c_tool", "title": "Technical indicators", "kind": "tool"},
    ],
    "disclaimer": DISCLAIMER,
}


def _brief_json(d: dict[str, Any]) -> str:
    return json.dumps(d)


def test_grounded_news_citation_is_kept() -> None:
    """A news citation whose URL was seen by a tool survives untouched."""
    brief = parse_final(_brief_json(_BRIEF), {"https://news.example.com/a"})
    assert {c.id for c in brief.citations} == {"c_news", "c_tool"}
    assert len(brief.news_highlights) == 1


def test_ungrounded_news_citation_dropped_and_bullet_removed() -> None:
    """When the only support for a bullet is a fabricated URL, drop both."""
    brief = parse_final(_brief_json(_BRIEF), seen_urls=set())  # nothing grounded
    ids = {c.id for c in brief.citations}
    assert "c_news" not in ids  # fabricated citation removed
    assert "c_tool" in ids  # tool citation always kept
    # the news_highlights bullet cited only the fabricated id -> dropped
    assert brief.news_highlights == []
    # tool-cited bullets are unaffected
    assert len(brief.bull_case) == 1


def test_anomaly_losing_all_support_falls_back_to_low_confidence() -> None:
    """An anomaly whose only citation is fabricated becomes low-confidence."""
    brief = parse_final(_brief_json(_BRIEF), seen_urls=set())
    a = brief.anomalies[0]
    assert a.confidence == "low"
    assert a.citations == []
    assert "No public cause" in a.explanation


def test_bullet_with_mixed_citations_keeps_grounded_one() -> None:
    """A bullet citing both a fabricated and a grounded id keeps the grounded id."""
    d = deepcopy(_BRIEF)
    d["risks"] = [{"text": "Mixed support.", "citations": ["c_news", "c_tool"]}]
    brief = parse_final(_brief_json(d), seen_urls=set())  # c_news ungrounded
    assert len(brief.risks) == 1
    assert brief.risks[0].citations == ["c_tool"]


def test_seen_urls_none_skips_grounding() -> None:
    """Backward-compat: without seen_urls, no grounding is applied."""
    brief = parse_final(_brief_json(_BRIEF))
    assert {c.id for c in brief.citations} == {"c_news", "c_tool"}
    assert len(brief.news_highlights) == 1
