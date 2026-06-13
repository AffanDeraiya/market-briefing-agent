"""Tests for src/schemas.py — MarketBrief parse + validation contract."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.schemas import DISCLAIMER, Anomaly, Bullet, Citation, MarketBrief, parse_brief

# ---------------------------------------------------------------------------
# Minimal-valid brief builder
# ---------------------------------------------------------------------------


def _valid_brief() -> dict:  # type: ignore[type-arg]
    """Return a minimal dict that passes all MarketBrief validators."""
    return {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "as_of": "2024-01-15",
        "period": "6mo",
        "snapshot": {
            "price": 185.50,
            "change_1d": 1.2,
            "change_1m": 3.4,
            "change_period": 8.1,
            "market_cap": 2_900_000_000_000,
            "pe": 28.5,
            "sector": "Technology",
        },
        "technical_summary": "Uptrend, RSI neutral, volume stable.",
        "anomalies": [
            {
                "date": "2024-01-10",
                "kind": "price_spike",
                "magnitude": "+5.2% (3.1σ)",
                "explanation": "Earnings beat expectations.",
                "confidence": "high",
                "citations": ["c1"],
            }
        ],
        "news_highlights": [{"text": "Apple reports record revenue.", "citations": ["c1"]}],
        "bull_case": [{"text": "Strong iPhone cycle ahead.", "citations": ["c1"]}],
        "bear_case": [{"text": "Macro headwinds.", "citations": ["c1"]}],
        "risks": [{"text": "Regulatory scrutiny.", "citations": ["c1"]}],
        "citations": [
            {
                "id": "c1",
                "url": "https://example.com/article",
                "title": "Apple Q1 Earnings",
                "kind": "news",
            }
        ],
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# 1. Valid brief parses from dict
# ---------------------------------------------------------------------------


def test_valid_brief_from_dict() -> None:
    brief = parse_brief(_valid_brief())
    assert isinstance(brief, MarketBrief)
    assert brief.ticker == "AAPL"
    assert brief.disclaimer == DISCLAIMER


# ---------------------------------------------------------------------------
# 2. Valid brief parses from JSON string
# ---------------------------------------------------------------------------


def test_valid_brief_from_json_string() -> None:
    raw_json = json.dumps(_valid_brief())
    brief = parse_brief(raw_json)
    assert isinstance(brief, MarketBrief)
    assert brief.ticker == "AAPL"


# ---------------------------------------------------------------------------
# 3. Unknown field is rejected (extra="forbid")
# ---------------------------------------------------------------------------


def test_unknown_field_rejected() -> None:
    d = _valid_brief()
    d["extra_field_that_should_not_exist"] = "oops"
    with pytest.raises(ValidationError):
        parse_brief(d)


# ---------------------------------------------------------------------------
# 4. Bullet with empty citations rejected — news_highlights
# ---------------------------------------------------------------------------


def test_bullet_empty_citations_news_highlights() -> None:
    d = _valid_brief()
    d["news_highlights"] = [{"text": "Some news.", "citations": []}]
    with pytest.raises(ValidationError):
        parse_brief(d)


# ---------------------------------------------------------------------------
# 5. Bullet with empty citations rejected — bull_case
# ---------------------------------------------------------------------------


def test_bullet_empty_citations_bull_case() -> None:
    d = _valid_brief()
    d["bull_case"] = [{"text": "Bullish point.", "citations": []}]
    with pytest.raises(ValidationError):
        parse_brief(d)


# ---------------------------------------------------------------------------
# 6. Anomaly: empty citations + confidence "high" → rejected
# ---------------------------------------------------------------------------


def test_anomaly_empty_citations_high_confidence_rejected() -> None:
    d = _valid_brief()
    d["anomalies"] = [
        {
            "date": "2024-01-10",
            "kind": "price_spike",
            "magnitude": "+5.2% (3.1σ)",
            "explanation": "No reason.",
            "confidence": "high",
            "citations": [],
        }
    ]
    with pytest.raises(ValidationError):
        parse_brief(d)


# ---------------------------------------------------------------------------
# 7. Anomaly: empty citations + confidence "low" → accepted
# ---------------------------------------------------------------------------


def test_anomaly_empty_citations_low_confidence_accepted() -> None:
    d = _valid_brief()
    d["anomalies"] = [
        {
            "date": "2024-01-10",
            "kind": "price_spike",
            "magnitude": "+5.2% (3.1σ)",
            "explanation": "No clear public cause found.",
            "confidence": "low",
            "citations": [],
        }
    ]
    brief = parse_brief(d)
    assert brief.anomalies[0].confidence == "low"
    assert brief.anomalies[0].citations == []


# ---------------------------------------------------------------------------
# 8. Citation kind="news" with url=None → rejected
# ---------------------------------------------------------------------------


def test_citation_news_without_url_rejected() -> None:
    d = _valid_brief()
    d["citations"] = [{"id": "c1", "url": None, "title": "Some Article", "kind": "news"}]
    with pytest.raises(ValidationError):
        parse_brief(d)


# ---------------------------------------------------------------------------
# 9. Citation kind="tool" with url=None → accepted
# ---------------------------------------------------------------------------


def test_citation_tool_without_url_accepted() -> None:
    d = _valid_brief()
    d["citations"] = [{"id": "c1", "url": None, "title": "Market Data Snapshot", "kind": "tool"}]
    brief = parse_brief(d)
    assert brief.citations[0].url is None
    assert brief.citations[0].kind == "tool"


# ---------------------------------------------------------------------------
# 10. Referenced-but-undefined citation id → rejected
# ---------------------------------------------------------------------------


def test_undefined_citation_id_rejected() -> None:
    d = _valid_brief()
    # bullet references "c99" which doesn't exist in citations list
    d["news_highlights"] = [{"text": "Some news.", "citations": ["c99"]}]
    with pytest.raises(ValidationError):
        parse_brief(d)


# ---------------------------------------------------------------------------
# 11. List cap: 6 news_highlights → rejected
# ---------------------------------------------------------------------------


def test_news_highlights_cap_6_rejected() -> None:
    d = _valid_brief()
    d["news_highlights"] = [{"text": f"News item {i}.", "citations": ["c1"]} for i in range(6)]
    with pytest.raises(ValidationError):
        parse_brief(d)


# ---------------------------------------------------------------------------
# 12. List cap: 5 bull_case → rejected
# ---------------------------------------------------------------------------


def test_bull_case_cap_5_rejected() -> None:
    d = _valid_brief()
    d["bull_case"] = [{"text": f"Bull point {i}.", "citations": ["c1"]} for i in range(5)]
    with pytest.raises(ValidationError):
        parse_brief(d)


# ---------------------------------------------------------------------------
# 13. List cap: 4 risks → rejected
# ---------------------------------------------------------------------------


def test_risks_cap_4_rejected() -> None:
    d = _valid_brief()
    d["risks"] = [{"text": f"Risk {i}.", "citations": ["c1"]} for i in range(4)]
    with pytest.raises(ValidationError):
        parse_brief(d)


# ---------------------------------------------------------------------------
# 14. Wrong disclaimer string → rejected
# ---------------------------------------------------------------------------


def test_wrong_disclaimer_rejected() -> None:
    d = _valid_brief()
    d["disclaimer"] = "This is not financial advice."
    with pytest.raises(ValidationError):
        parse_brief(d)


# ---------------------------------------------------------------------------
# 15. Malformed JSON string → raises ValueError (or json error)
# ---------------------------------------------------------------------------


def test_malformed_json_raises() -> None:
    with pytest.raises((ValueError, Exception)):
        parse_brief("{not valid json}")


# ---------------------------------------------------------------------------
# 16. bear_case cap: 5 items → rejected
# ---------------------------------------------------------------------------


def test_bear_case_cap_5_rejected() -> None:
    d = _valid_brief()
    d["bear_case"] = [{"text": f"Bear point {i}.", "citations": ["c1"]} for i in range(5)]
    with pytest.raises(ValidationError):
        parse_brief(d)


# ---------------------------------------------------------------------------
# 17. news_highlights at exactly 5 → accepted
# ---------------------------------------------------------------------------


def test_news_highlights_5_accepted() -> None:
    d = _valid_brief()
    d["news_highlights"] = [{"text": f"News {i}.", "citations": ["c1"]} for i in range(5)]
    brief = parse_brief(d)
    assert len(brief.news_highlights) == 5


# ---------------------------------------------------------------------------
# 18. Anomaly undefined citation id → rejected
# ---------------------------------------------------------------------------


def test_anomaly_undefined_citation_rejected() -> None:
    d = _valid_brief()
    d["anomalies"] = [
        {
            "date": "2024-01-10",
            "kind": "price_drop",
            "magnitude": "-4.0% (2.8σ)",
            "explanation": "Some explanation.",
            "confidence": "medium",
            "citations": ["c99"],  # "c99" not in d["citations"]
        }
    ]
    with pytest.raises(ValidationError):
        parse_brief(d)


# ---------------------------------------------------------------------------
# 19. Citation kind="web" with url=None → rejected
# ---------------------------------------------------------------------------


def test_citation_web_without_url_rejected() -> None:
    d = _valid_brief()
    d["citations"] = [{"id": "c1", "url": None, "title": "Some Web Page", "kind": "web"}]
    with pytest.raises(ValidationError):
        parse_brief(d)


# ---------------------------------------------------------------------------
# 20. Bullet model directly: extra field rejected
# ---------------------------------------------------------------------------


def test_bullet_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        Bullet(text="Some text.", citations=["c1"], extra_field="nope")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# 21. Citation model directly: tool kind with url=None accepted
# ---------------------------------------------------------------------------


def test_citation_model_tool_url_none() -> None:
    c = Citation(id="c1", url=None, title="Snapshot", kind="tool")
    assert c.url is None


# ---------------------------------------------------------------------------
# 22. Anomaly model directly: medium confidence with citations accepted
# ---------------------------------------------------------------------------


def test_anomaly_medium_confidence_with_citations() -> None:
    a = Anomaly(
        date="2024-02-01",
        kind="volume_surge",
        magnitude="volume 4.5× 30d avg",
        explanation="Unusual trading activity around earnings.",
        confidence="medium",
        citations=["c1"],
    )
    assert a.confidence == "medium"
    assert len(a.citations) == 1
