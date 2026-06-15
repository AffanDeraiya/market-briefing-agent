"""Offline tests for the eval harness (replay, checks, report).

All tests are fully offline — no network calls, no LLM API keys required.
The committed aapl_3mo.json cassette is used as the primary fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.schemas import DISCLAIMER, MarketBrief, parse_brief

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CASSETTES_DIR = Path(__file__).parent.parent / "evals" / "cassettes"
_AAPL_CASSETTE = _CASSETTES_DIR / "aapl_3mo.json"

# ---------------------------------------------------------------------------
# Minimal valid brief dict (for constructing MarketBrief fixtures)
# ---------------------------------------------------------------------------

_VALID_BRIEF_DICT: dict[str, Any] = {
    "ticker": "AAPL",
    "name": "Apple Inc.",
    "as_of": "2024-01-15",
    "period": "3mo",
    "snapshot": {
        "price": 185.50,
        "change_1d": 1.2,
        "change_1m": 3.4,
        "change_period": 8.1,
        "market_cap": 2_900_000_000_000,
        "pe": 28.5,
        "sector": "Technology",
    },
    "indicators": {"rsi14": 44.5, "rsi_signal": "neutral"},
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
# Test 1 — replay_cassette reproduces the brief
# ---------------------------------------------------------------------------


def test_replay_aapl_cassette_reproduces_brief() -> None:
    """Replaying aapl_3mo.json offline produces a valid MarketBrief for AAPL."""
    from evals.replay import replay_cassette

    result = replay_cassette(_AAPL_CASSETTE)

    assert result.error is None, f"unexpected replay error: {result.error}"
    assert result.brief is not None, "expected a brief from replay"
    assert result.brief.ticker == "AAPL"


# ---------------------------------------------------------------------------
# Test 2 — citation faithfulness is perfect on the recorded run
# ---------------------------------------------------------------------------


def test_citation_faithfulness_perfect_on_recorded_run() -> None:
    """All citations in the AAPL cassette should be faithful (score == 1.0)."""
    from evals.checks import citation_faithfulness
    from evals.replay import replay_cassette

    result = replay_cassette(_AAPL_CASSETTE)
    assert result.brief is not None

    score, unfaithful_ids = citation_faithfulness(result.brief, result.tool_io)

    assert score == pytest.approx(1.0), f"faithfulness < 1.0; unfaithful: {unfaithful_ids}"
    assert unfaithful_ids == []


# ---------------------------------------------------------------------------
# Test 3 — structure compliance is perfect on the recorded run
# ---------------------------------------------------------------------------


def test_structure_compliance_perfect_on_recorded_run() -> None:
    """All structure checks should pass for the AAPL cassette brief."""
    from evals.checks import structure_compliance
    from evals.replay import replay_cassette

    result = replay_cassette(_AAPL_CASSETTE)
    assert result.brief is not None

    score, failed = structure_compliance(result.brief)

    assert score == pytest.approx(1.0), f"structure < 1.0; failed checks: {failed}"
    assert failed == []


# ---------------------------------------------------------------------------
# Test 4 — grounded_urls extracts nested URLs
# ---------------------------------------------------------------------------


def test_grounded_urls_extracts_news_urls() -> None:
    """grounded_urls correctly extracts a URL from a nested tool output."""
    from evals.checks import grounded_urls

    fake_output = json.dumps({"results": [{"url": "https://x.com/a", "title": "Test"}]})
    tool_io: list[dict[str, Any]] = [
        {"seq": 1, "name": "get_company_news", "input": {}, "output": fake_output}
    ]

    urls = grounded_urls(tool_io)

    assert "https://x.com/a" in urls


# ---------------------------------------------------------------------------
# Test 5 — citation_faithfulness flags a fabricated URL
# ---------------------------------------------------------------------------


def test_citation_faithfulness_flags_fabricated_url() -> None:
    """A news citation whose URL is absent from tool_io must be flagged."""
    from evals.checks import citation_faithfulness

    # Build a brief whose news citation URL does NOT appear in any tool output.
    brief_dict: dict[str, Any] = {
        **_VALID_BRIEF_DICT,
        "citations": [
            {
                "id": "c1",
                "url": "https://fabricated-url-not-in-tools.example.com/article",
                "title": "Fabricated Article",
                "kind": "news",
            }
        ],
    }
    brief: MarketBrief = parse_brief(brief_dict)

    # tool_io contains a different URL — NOT the citation's URL
    tool_io: list[dict[str, Any]] = [
        {
            "seq": 1,
            "name": "get_company_news",
            "input": {},
            "output": json.dumps({"results": [{"url": "https://real-source.com/news"}]}),
        }
    ]

    score, unfaithful_ids = citation_faithfulness(brief, tool_io)

    assert score < 1.0, "expected score < 1.0 for a fabricated URL"
    assert "c1" in unfaithful_ids


# ---------------------------------------------------------------------------
# Test 6 — evaluate_all + aggregate over the real cassettes directory
# ---------------------------------------------------------------------------


def test_evaluate_all_and_aggregate() -> None:
    """evaluate_all over the real cassettes dir returns >=1 RunMetrics; aggregate passes."""
    from evals.report import aggregate, evaluate_all

    metrics = evaluate_all(_CASSETTES_DIR)

    assert len(metrics) >= 1, "expected at least one RunMetrics from the cassettes dir"

    agg = aggregate(metrics)

    assert agg["n"] >= 1
    assert agg["all_pass"] is True, (
        f"aggregate all_pass=False; "
        f"faithfulness={agg['mean_faithfulness']:.2f}, "
        f"structure={agg['mean_structure']:.2f}"
    )
