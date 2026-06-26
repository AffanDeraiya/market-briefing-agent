"""Tests for the optional Signal field on MarketBrief.

Covers schema validation (tests 1-6), citation resolution (test 6),
grounding neutralization (test 7), and deterministic as_of stamping (test 8).
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from src.agents.market_brief.state import RunState
from src.agents.market_brief.utils.parsing import (
    _NO_SIGNAL_RATIONALE,
    attach_market_data,
    parse_final,
)
from src.schemas import DISCLAIMER, Signal, parse_brief

# ---------------------------------------------------------------------------
# Shared minimal-valid brief dict (tool citation so grounding is irrelevant)
# ---------------------------------------------------------------------------

_BRIEF: dict[str, Any] = {
    "ticker": "AAPL",
    "name": "Apple Inc.",
    "as_of": "2026-06-18",
    "period": "6mo",
    "snapshot": {
        "price": 185.50,
        "change_1d": 1.2,
        "change_1m": 3.4,
        "change_period": 8.1,
        "sector": "Technology",
    },
    "technical_summary": "Uptrend, RSI neutral.",
    "anomalies": [],
    "news_highlights": [],
    "bull_case": [{"text": "Strong iPhone cycle ahead.", "citations": ["c_tool"]}],
    "bear_case": [{"text": "Macro headwinds.", "citations": ["c_tool"]}],
    "risks": [{"text": "Regulatory scrutiny.", "citations": ["c_tool"]}],
    "citations": [
        {"id": "c_tool", "title": "Technical indicators", "kind": "tool"},
    ],
    "disclaimer": DISCLAIMER,
}

# A news citation that can be added when tests need a grounded/ungrounded pair
_NEWS_CITATION: dict[str, Any] = {
    "id": "c_news",
    "url": "https://news.example.com/article",
    "title": "Apple Q1 Earnings",
    "kind": "news",
}
_NEWS_URL = "https://news.example.com/article"


def _brief_with_signal(signal: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of _BRIEF that includes a top-level signal object."""
    d = deepcopy(_BRIEF)
    d["signal"] = signal
    return d


def _brief_json(d: dict[str, Any]) -> str:
    return json.dumps(d)


# ---------------------------------------------------------------------------
# Test 1 — MarketBrief with valid grounded signal round-trips
# ---------------------------------------------------------------------------


def test_valid_signal_round_trips() -> None:
    """A MarketBrief dict with a valid signal parses correctly; fields round-trip."""
    d = _brief_with_signal(
        {
            "stance": "buy",
            "rationale": "Strong earnings momentum and expanding margins.",
            "citations": ["c_tool"],
            "confidence": "high",
        }
    )
    brief = parse_brief(d)

    assert brief.signal is not None
    assert brief.signal.stance == "buy"
    assert brief.signal.rationale == "Strong earnings momentum and expanding margins."
    assert brief.signal.confidence == "high"
    assert brief.signal.citations == ["c_tool"]
    # as_of is stamped later by attach_market_data; model default is ""
    assert brief.signal.as_of == ""


# ---------------------------------------------------------------------------
# Test 2 — MarketBrief without signal → signal is None
# ---------------------------------------------------------------------------


def test_no_signal_is_none() -> None:
    """A brief dict without a signal field parses to brief.signal == None."""
    brief = parse_brief(deepcopy(_BRIEF))
    assert brief.signal is None


# ---------------------------------------------------------------------------
# Test 3 — signal with stance "buy" and citations=[] → ValidationError
# ---------------------------------------------------------------------------


def test_signal_buy_empty_citations_rejected() -> None:
    """stance='buy' with citations=[] must be rejected (citations required unless neutral)."""
    d = _brief_with_signal(
        {
            "stance": "buy",
            "rationale": "Strong growth prospects.",
            "citations": [],
            "confidence": "medium",
        }
    )
    with pytest.raises(ValidationError):
        parse_brief(d)


# ---------------------------------------------------------------------------
# Test 4 — signal with stance "neutral" and citations=[] → valid
# ---------------------------------------------------------------------------


def test_signal_neutral_empty_citations_accepted() -> None:
    """stance='neutral' with citations=[] is valid — neutral doesn't require citations."""
    d = _brief_with_signal(
        {
            "stance": "neutral",
            "rationale": "Insufficient evidence for a directional call.",
            "citations": [],
            "confidence": "low",
        }
    )
    brief = parse_brief(d)
    assert brief.signal is not None
    assert brief.signal.stance == "neutral"
    assert brief.signal.citations == []


# ---------------------------------------------------------------------------
# Test 5 — signal with empty/whitespace rationale → ValidationError
# ---------------------------------------------------------------------------


def test_signal_empty_rationale_rejected() -> None:
    """signal.rationale must be non-empty; blank/whitespace-only raises ValidationError."""
    for bad_rationale in ("", "   ", "\t\n"):
        d = _brief_with_signal(
            {
                "stance": "neutral",
                "rationale": bad_rationale,
                "citations": [],
                "confidence": "low",
            }
        )
        with pytest.raises(ValidationError):
            parse_brief(d)


# ---------------------------------------------------------------------------
# Test 6 — signal citing an undefined citation id → ValidationError
# ---------------------------------------------------------------------------


def test_signal_undefined_citation_id_rejected() -> None:
    """A signal that references a citation id absent from top-level citations → rejected."""
    d = _brief_with_signal(
        {
            "stance": "accumulate",
            "rationale": "Pipeline looks solid based on analyst coverage.",
            "citations": ["c_ghost"],  # "c_ghost" not in d["citations"]
            "confidence": "medium",
        }
    )
    with pytest.raises(ValidationError):
        parse_brief(d)


# ---------------------------------------------------------------------------
# Test 7 — grounding neutralizes signal when its only citation is ungrounded
# ---------------------------------------------------------------------------


def test_grounding_neutralizes_signal_when_all_citations_fabricated() -> None:
    """parse_final with seen_urls that exclude the signal's news URL neutralizes the signal."""
    d = deepcopy(_BRIEF)
    # Add a news citation so we have a grounded anchor; signal references it
    d["citations"].append(_NEWS_CITATION)
    d["signal"] = {
        "stance": "buy",
        "rationale": "Upside driven by strong news coverage.",
        "citations": ["c_news"],
        "confidence": "high",
    }
    # Also add a news_highlights bullet that references c_news so the brief
    # stays valid after grounding (the bullet will be dropped too, which is fine).
    d["news_highlights"] = [{"text": "Strong results.", "citations": ["c_news"]}]

    # seen_urls does NOT include the news article → c_news is fabricated
    brief = parse_final(_brief_json(d), seen_urls=set())

    assert brief.signal is not None
    assert brief.signal.stance == "neutral"
    assert brief.signal.confidence == "low"
    assert brief.signal.citations == []
    assert brief.signal.rationale == _NO_SIGNAL_RATIONALE


# ---------------------------------------------------------------------------
# Test 8 — attach_market_data stamps signal.as_of from brief.as_of
# ---------------------------------------------------------------------------


def test_attach_market_data_stamps_signal_as_of() -> None:
    """attach_market_data must set signal.as_of = brief.as_of."""
    d = _brief_with_signal(
        {
            "stance": "accumulate",
            "as_of": "",  # LLM omits / leaves blank
            "rationale": "Steady growth trajectory.",
            "citations": ["c_tool"],
            "confidence": "medium",
        }
    )
    brief = parse_brief(d)
    assert brief.signal is not None
    assert brief.signal.as_of == ""  # not yet stamped

    state = RunState(ticker="AAPL", period="6mo")
    attach_market_data(state, brief)

    assert brief.signal.as_of == "2026-06-18"  # stamped from brief.as_of


# ---------------------------------------------------------------------------
# Bonus — Signal model directly: extra field rejected
# ---------------------------------------------------------------------------


def test_signal_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        Signal(  # type: ignore[call-arg]
            stance="neutral",
            rationale="No clear call.",
            citations=[],
            confidence="low",
            unexpected_field="nope",
        )


# ---------------------------------------------------------------------------
# Bonus — All non-neutral stances require citations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stance", ["accumulate", "reduce", "sell"])
def test_non_neutral_stances_require_citations(stance: str) -> None:
    """Every non-neutral stance must have at least one citation."""
    d = _brief_with_signal(
        {
            "stance": stance,
            "rationale": "Some rationale.",
            "citations": [],
            "confidence": "low",
        }
    )
    with pytest.raises(ValidationError):
        parse_brief(d)
