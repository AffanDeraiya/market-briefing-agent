"""Tests for utils/verify.py — the Claim Verifier logic.

Covers:
1. count_claims on a known brief.
2. run_verification(verify_llm=False) on a CLEAN brief → None, backend not called.
3. LLM layer: unsupported bullet → dropped; partial anomaly → confidence downgraded;
   unsupported signal → neutralized.
4. Token counting: input/output_tokens incremented; iterations/tool_calls_made unchanged.
5. LLM layer returning malformed JSON → no crash, falls back cleanly.
6. Deterministic signal-consistency check: buy stance + empty bull_case → neutralized.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from src.agents.market_brief.state import RunState
from src.agents.market_brief.utils.verify import count_claims, run_verification
from src.llm import LLMBackend, LLMResponse, ToolResult, ToolSpec, Turn, Usage
from src.schemas import DISCLAIMER, MarketBrief, Verification, parse_brief

# ---------------------------------------------------------------------------
# Shared minimal-valid brief dict
# ---------------------------------------------------------------------------

_BRIEF_DICT: dict[str, Any] = {
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
    "anomalies": [
        {
            "date": "2026-05-10",
            "kind": "price_spike",
            "magnitude": "+4.5% (2.8σ)",
            "explanation": "Earnings beat expectations.",
            "confidence": "high",
            "citations": ["c_tool"],
        }
    ],
    "news_highlights": [{"text": "Apple reports record revenue.", "citations": ["c_tool"]}],
    "bull_case": [{"text": "Strong iPhone cycle ahead.", "citations": ["c_tool"]}],
    "bear_case": [{"text": "Macro headwinds.", "citations": ["c_tool"]}],
    "risks": [{"text": "Regulatory scrutiny.", "citations": ["c_tool"]}],
    "signal": {
        "stance": "accumulate",
        "rationale": "Steady growth trajectory justified by bull-case evidence.",
        "citations": ["c_tool"],
        "confidence": "medium",
    },
    "citations": [
        {"id": "c_tool", "title": "Technical indicators", "kind": "tool"},
    ],
    "disclaimer": DISCLAIMER,
}


def _make_brief(overrides: dict[str, Any] | None = None) -> MarketBrief:
    """Build a valid MarketBrief from _BRIEF_DICT, with optional overrides."""
    d = deepcopy(_BRIEF_DICT)
    if overrides:
        d.update(overrides)
    return parse_brief(d)


def _make_run(**kwargs: Any) -> RunState:
    """Build a minimal RunState with optional kwarg overrides."""
    defaults: dict[str, Any] = {"ticker": "AAPL", "period": "6mo"}
    defaults.update(kwargs)
    return RunState(**defaults)


# ---------------------------------------------------------------------------
# FakeBackend — replicates the pattern from test_agent_loop.py
# ---------------------------------------------------------------------------


class FakeBackend(LLMBackend):
    """Replays a pre-built sequence of LLMResponse objects in order."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.model = "fake-model"
        self._responses = list(responses)
        self._i = 0
        self.call_count = 0

    def complete(
        self,
        *,
        system: str,
        history: list[Turn],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> LLMResponse:
        self.call_count += 1
        if self._i >= len(self._responses):
            raise IndexError(
                f"FakeBackend exhausted: called {self.call_count} times "
                f"but only {len(self._responses)} responses were provided"
            )
        resp = self._responses[self._i]
        self._i += 1
        return resp


def _fake_verifier_response(verdicts: list[dict[str, Any]]) -> LLMResponse:
    """Build an LLMResponse whose text is a valid verifier JSON payload."""
    payload = json.dumps({"verdicts": verdicts})
    return LLMResponse(
        text=payload,
        tool_calls=[],
        usage=Usage(input_tokens=100, output_tokens=50),
    )


# ---------------------------------------------------------------------------
# Test 1 — count_claims
# ---------------------------------------------------------------------------


def test_count_claims_known_brief() -> None:
    """count_claims returns the correct total for a known brief structure."""
    brief = _make_brief()
    # news_highlights(1) + bull_case(1) + bear_case(1) + risks(1)
    # + anomaly with citations(1) + signal stance != neutral(1) = 6
    assert count_claims(brief) == 6


def test_count_claims_neutral_signal_excluded() -> None:
    """A neutral signal is not auditable and should not be counted."""
    d = deepcopy(_BRIEF_DICT)
    d["signal"] = {
        "stance": "neutral",
        "rationale": "Mixed evidence.",
        "citations": [],
        "confidence": "low",
    }
    brief = parse_brief(d)
    # same as above minus the signal = 5
    assert count_claims(brief) == 5


def test_count_claims_anomaly_without_citations_excluded() -> None:
    """An anomaly with no citations (low confidence) is not auditable."""
    d = deepcopy(_BRIEF_DICT)
    d["anomalies"] = [
        {
            "date": "2026-05-10",
            "kind": "price_spike",
            "magnitude": "+4.5%",
            "explanation": "Unknown cause.",
            "confidence": "low",
            "citations": [],
        }
    ]
    brief = parse_brief(d)
    # news(1) + bull(1) + bear(1) + risks(1) + anomaly excluded(0) + signal(1) = 5
    assert count_claims(brief) == 5


def test_count_claims_empty_brief() -> None:
    """A brief with no bullets, no signal, and no cited anomalies has 0 claims."""
    d = deepcopy(_BRIEF_DICT)
    d["news_highlights"] = []
    d["bull_case"] = []
    d["bear_case"] = []
    d["risks"] = []
    d["anomalies"] = [
        {
            "date": "2026-05-10",
            "kind": "price_spike",
            "magnitude": "+4.5%",
            "explanation": "No cause found.",
            "confidence": "low",
            "citations": [],
        }
    ]
    d["signal"] = {
        "stance": "neutral",
        "rationale": "No clear call.",
        "citations": [],
        "confidence": "low",
    }
    brief = parse_brief(d)
    assert count_claims(brief) == 0


# ---------------------------------------------------------------------------
# Test 2 — deterministic-only on clean brief → None, backend not called
# ---------------------------------------------------------------------------


def test_clean_brief_returns_none_no_backend_call() -> None:
    """run_verification(verify_llm=False) on a clean brief returns None.

    The clean brief has bull_case items to match the accumulate stance,
    so the deterministic layer has nothing to flag.
    """
    brief = _make_brief()
    run = _make_run()
    backend = FakeBackend([])  # empty — must NOT be called

    result = run_verification(brief, run, backend=backend, verify_llm=False)

    assert result is None
    assert brief.verification is None
    assert backend.call_count == 0


def test_clean_brief_llm_false_brief_unchanged() -> None:
    """verify_llm=False must not mutate a valid brief in any way."""
    brief = _make_brief()
    original_signal_stance = brief.signal.stance if brief.signal else None
    original_bull_len = len(brief.bull_case)

    run = _make_run()
    run_verification(brief, run, backend=None, verify_llm=False)

    assert brief.signal is not None
    assert brief.signal.stance == original_signal_stance
    assert len(brief.bull_case) == original_bull_len


# ---------------------------------------------------------------------------
# Test 3 — LLM layer: unsupported bullet dropped; partial anomaly downgraded;
#           unsupported signal neutralized
# ---------------------------------------------------------------------------


def test_llm_unsupported_bullet_is_dropped() -> None:
    """An 'unsupported' verdict on a bull_case bullet removes it from the list."""
    brief = _make_brief()
    run = _make_run()

    backend = FakeBackend(
        [
            _fake_verifier_response(
                [
                    {"target": "bull_case:0", "verdict": "unsupported", "note": "Not in evidence."},
                ]
            )
        ]
    )

    result = run_verification(brief, run, backend=backend, verify_llm=True)

    assert result is not None
    assert isinstance(result, Verification)
    # The bullet was dropped
    assert len(brief.bull_case) == 0
    # One verdict recorded
    assert result.dropped == 1
    assert result.checked == 1
    # brief.verification is set
    assert brief.verification is result


def test_llm_partial_anomaly_confidence_downgraded() -> None:
    """A 'partial' verdict on an anomaly downgrades its confidence one notch."""
    brief = _make_brief()
    # Anomaly starts at "high"
    assert brief.anomalies[0].confidence == "high"

    run = _make_run()
    backend = FakeBackend(
        [
            _fake_verifier_response(
                [
                    {"target": "anomaly:2026-05-10", "verdict": "partial", "note": "Weak link."},
                ]
            )
        ]
    )

    result = run_verification(brief, run, backend=backend, verify_llm=True)

    assert result is not None
    # high → medium
    assert brief.anomalies[0].confidence == "medium"
    assert result.adjusted == 1
    assert result.dropped == 0


def test_llm_partial_anomaly_already_low_no_change() -> None:
    """A 'partial' verdict on an already-low anomaly is 'kept', not 'downgraded'."""
    d = deepcopy(_BRIEF_DICT)
    # Make anomaly low confidence (citations required to be empty per schema)
    d["anomalies"] = [
        {
            "date": "2026-05-10",
            "kind": "price_spike",
            "magnitude": "+4.5%",
            "explanation": "No cause found.",
            "confidence": "low",
            "citations": [],
        }
    ]
    brief = parse_brief(d)

    run = _make_run()
    backend = FakeBackend(
        [
            _fake_verifier_response(
                [
                    {"target": "anomaly:2026-05-10", "verdict": "partial", "note": "Weak."},
                ]
            )
        ]
    )

    run_verification(brief, run, backend=backend, verify_llm=True)

    # anomaly:2026-05-10 has no citations, so count_claims excludes it,
    # meaning the claims_block will be empty for anomalies. The returned target
    # won't match a valid target → ignored. Let's check overall.
    # The anomaly target won't be in valid_targets since it has no citations.
    # So verdict is ignored, result could be None (no other claims mentioned).
    # The brief should be untouched.
    assert brief.anomalies[0].confidence == "low"


def test_llm_unsupported_signal_neutralized() -> None:
    """An 'unsupported' verdict on the signal neutralizes it."""
    brief = _make_brief()
    assert brief.signal is not None
    assert brief.signal.stance == "accumulate"

    run = _make_run()
    backend = FakeBackend(
        [
            _fake_verifier_response(
                [
                    {
                        "target": "signal",
                        "verdict": "unsupported",
                        "note": "Evidence insufficient.",
                    },
                ]
            )
        ]
    )

    result = run_verification(brief, run, backend=backend, verify_llm=True)

    assert result is not None
    assert brief.signal.stance == "neutral"
    assert brief.signal.confidence == "low"
    assert brief.signal.citations == []
    assert result.adjusted == 1


def test_llm_supported_verdict_keeps_brief_unchanged() -> None:
    """A 'supported' verdict results in action='kept' and no mutations."""
    brief = _make_brief()
    original_bull = deepcopy(brief.bull_case)

    run = _make_run()
    backend = FakeBackend(
        [
            _fake_verifier_response(
                [
                    {"target": "bull_case:0", "verdict": "supported", "note": ""},
                ]
            )
        ]
    )

    result = run_verification(brief, run, backend=backend, verify_llm=True)

    assert result is not None
    assert brief.bull_case == original_bull
    assert result.supported == 1
    assert result.dropped == 0
    assert result.adjusted == 0


def test_llm_verification_summary_counts() -> None:
    """Verification summary counts are computed correctly across mixed verdicts."""
    brief = _make_brief()
    run = _make_run()

    backend = FakeBackend(
        [
            _fake_verifier_response(
                [
                    {"target": "news_highlights:0", "verdict": "supported", "note": ""},
                    {"target": "bull_case:0", "verdict": "unsupported", "note": "Not backed."},
                    {"target": "anomaly:2026-05-10", "verdict": "partial", "note": "Weak."},
                    {"target": "signal", "verdict": "supported", "note": ""},
                ]
            )
        ]
    )

    result = run_verification(brief, run, backend=backend, verify_llm=True)

    assert result is not None
    assert result.checked == 4
    assert result.supported == 2  # news + signal
    assert result.adjusted == 1  # anomaly confidence_downgraded
    assert result.dropped == 1  # bull_case bullet


# ---------------------------------------------------------------------------
# Test 4 — Token counting
# ---------------------------------------------------------------------------


def test_token_counting_incremented_by_verifier() -> None:
    """After LLM layer runs, run.input/output_tokens increase by FakeBackend usage.
    run.iterations and run.tool_calls_made must stay unchanged.
    """
    brief = _make_brief()
    run = _make_run()
    run.input_tokens = 200
    run.output_tokens = 100
    run.iterations = 3
    run.tool_calls_made = 7

    verifier_usage = Usage(input_tokens=100, output_tokens=50)
    backend = FakeBackend(
        [
            LLMResponse(
                text=json.dumps({"verdicts": []}),
                tool_calls=[],
                usage=verifier_usage,
            )
        ]
    )

    run_verification(brief, run, backend=backend, verify_llm=True)

    assert run.input_tokens == 200 + 100
    assert run.output_tokens == 100 + 50
    assert run.iterations == 3  # unchanged
    assert run.tool_calls_made == 7  # unchanged


# ---------------------------------------------------------------------------
# Test 5 — Malformed JSON from LLM → no crash, falls back cleanly
# ---------------------------------------------------------------------------


def test_malformed_json_falls_back_gracefully() -> None:
    """If the LLM returns malformed JSON, the verifier does not crash.

    It falls back to deterministic-only (clean brief → None).
    """
    brief = _make_brief()
    run = _make_run()

    backend = FakeBackend(
        [
            LLMResponse(
                text="this is not json { at all",
                tool_calls=[],
                usage=Usage(input_tokens=10, output_tokens=5),
            )
        ]
    )

    # Should not raise
    result = run_verification(brief, run, backend=backend, verify_llm=True)

    # Clean brief → deterministic layer has nothing to flag → None
    assert result is None
    # Brief is not corrupted
    assert brief.signal is not None
    assert brief.signal.stance == "accumulate"
    assert len(brief.bull_case) == 1


def test_malformed_json_missing_verdicts_key_falls_back() -> None:
    """LLM returns valid JSON but without the 'verdicts' key → falls back."""
    brief = _make_brief()
    run = _make_run()

    backend = FakeBackend(
        [
            LLMResponse(
                text=json.dumps({"result": "unexpected shape"}),
                tool_calls=[],
                usage=Usage(input_tokens=10, output_tokens=5),
            )
        ]
    )

    result = run_verification(brief, run, backend=backend, verify_llm=True)

    # Falls back cleanly — clean brief, so None
    assert result is None
    assert len(brief.bull_case) == 1  # unchanged


def test_backend_exception_falls_back_gracefully() -> None:
    """If the backend raises, the verifier falls back (no crash, no corruption)."""

    class BrokenBackend(LLMBackend):
        model = "broken"

        def complete(
            self,
            *,
            system: str,
            history: list[Turn],
            tools: list[ToolSpec],
            max_tokens: int,
        ) -> LLMResponse:
            raise RuntimeError("network error")

    brief = _make_brief()
    run = _make_run()

    result = run_verification(brief, run, backend=BrokenBackend(), verify_llm=True)

    # Falls back to deterministic-only; clean brief → None
    assert result is None
    assert brief.signal is not None
    assert brief.signal.stance == "accumulate"


# ---------------------------------------------------------------------------
# Test 6 — Deterministic signal-consistency check
# ---------------------------------------------------------------------------


def test_deterministic_buy_stance_empty_bull_case_neutralized() -> None:
    """Deterministic check: buy stance + empty bull_case → signal neutralized."""
    d = deepcopy(_BRIEF_DICT)
    d["bull_case"] = []
    # bear_case stays but bull_case is empty; signal is "buy"
    d["signal"] = {
        "stance": "buy",
        "rationale": "Great opportunity.",
        "citations": ["c_tool"],
        "confidence": "high",
    }
    # bear_case and risks still have bullets referencing c_tool
    brief = parse_brief(d)
    assert brief.signal is not None
    assert brief.signal.stance == "buy"
    assert len(brief.bull_case) == 0

    run = _make_run()
    backend = FakeBackend([])  # must NOT be called when verify_llm=False

    result = run_verification(brief, run, backend=backend, verify_llm=False)

    assert result is not None
    assert isinstance(result, Verification)

    # Signal was neutralized
    assert brief.signal.stance == "neutral"
    assert brief.signal.confidence == "low"
    assert brief.signal.citations == []

    # Exactly one verdict emitted
    assert result.checked == 1
    assert result.supported == 0
    assert result.adjusted == 1  # neutralized counts as adjusted
    assert result.dropped == 0

    v = result.verdicts[0]
    assert v.target == "signal"
    assert v.verdict == "unsupported"
    assert v.action == "neutralized"

    # backend was not called
    assert backend.call_count == 0


def test_deterministic_accumulate_empty_bull_case_neutralized() -> None:
    """Deterministic check: accumulate stance + empty bull_case → neutralized (same rule)."""
    d = deepcopy(_BRIEF_DICT)
    d["bull_case"] = []
    d["signal"] = {
        "stance": "accumulate",
        "rationale": "Moderate upside.",
        "citations": ["c_tool"],
        "confidence": "medium",
    }
    brief = parse_brief(d)

    run = _make_run()
    result = run_verification(brief, run, backend=None, verify_llm=False)

    assert result is not None
    assert brief.signal is not None
    assert brief.signal.stance == "neutral"
    assert result.adjusted == 1


def test_deterministic_buy_with_bull_case_not_fired() -> None:
    """Deterministic check must NOT fire when buy stance has non-empty bull_case."""
    brief = _make_brief()  # accumulate with bull_case[1]
    run = _make_run()

    result = run_verification(brief, run, backend=None, verify_llm=False)

    assert result is None  # no deterministic issue → None
    assert brief.signal is not None
    assert brief.signal.stance == "accumulate"  # unchanged


def test_deterministic_neutral_empty_bull_case_not_fired() -> None:
    """Deterministic check must NOT fire for neutral stance, even with empty bull_case."""
    d = deepcopy(_BRIEF_DICT)
    d["bull_case"] = []
    d["signal"] = {
        "stance": "neutral",
        "rationale": "Mixed signals.",
        "citations": [],
        "confidence": "low",
    }
    brief = parse_brief(d)

    run = _make_run()
    result = run_verification(brief, run, backend=None, verify_llm=False)

    assert result is None  # no violation → None


# ---------------------------------------------------------------------------
# Test 7 — verify_llm=False always skips backend
# ---------------------------------------------------------------------------


def test_verify_llm_false_skips_backend_even_if_provided() -> None:
    """verify_llm=False must never call backend.complete regardless of what is passed."""
    brief = _make_brief()
    run = _make_run()

    backend = FakeBackend(
        [
            _fake_verifier_response(
                [{"target": "bull_case:0", "verdict": "unsupported", "note": "x"}]
            )
        ]
    )

    run_verification(brief, run, backend=backend, verify_llm=False)

    assert backend.call_count == 0
    # Brief must be untouched (clean brief, deterministic layer has nothing to flag)
    assert len(brief.bull_case) == 1


# ---------------------------------------------------------------------------
# Test 8 — Verification model stored on brief
# ---------------------------------------------------------------------------


def test_verification_set_on_brief() -> None:
    """brief.verification is set to the returned Verification object."""
    brief = _make_brief()
    run = _make_run()

    backend = FakeBackend(
        [
            _fake_verifier_response(
                [
                    {"target": "bear_case:0", "verdict": "supported", "note": ""},
                ]
            )
        ]
    )

    result = run_verification(brief, run, backend=backend, verify_llm=True)

    assert result is not None
    assert brief.verification is result
    assert brief.verification.checked == 1


# ---------------------------------------------------------------------------
# Test 9 — Unknown target from LLM is ignored
# ---------------------------------------------------------------------------


def test_unknown_target_from_llm_ignored() -> None:
    """An LLM verdict targeting a non-existent claim is silently ignored."""
    brief = _make_brief()
    run = _make_run()

    backend = FakeBackend(
        [
            _fake_verifier_response(
                [
                    {"target": "ghost_section:99", "verdict": "unsupported", "note": "fake"},
                ]
            )
        ]
    )

    # Should not crash; the ghost target is ignored
    result = run_verification(brief, run, backend=backend, verify_llm=True)

    # No valid verdicts → deterministic clean → None or empty LLM set
    # ghost_section:99 is not a valid target so it's excluded
    # With no valid verdicts from LLM and no det verdicts, result is None
    assert result is None


# ---------------------------------------------------------------------------
# Test 10 — history tool results included in evidence
# ---------------------------------------------------------------------------


def test_evidence_includes_tool_result_turns() -> None:
    """Tool-result content in run.history is included in the evidence block sent to verifier."""
    brief = _make_brief()
    run = _make_run()

    # Add a tool-result turn to history
    tool_turn = Turn(
        role="tool",
        tool_results=[
            ToolResult(
                call_id="tc1",
                name="get_company_news",
                content='{"articles": [{"title": "Apple beats earnings", "url": "https://ex.com/1"}]}',
                is_error=False,
            )
        ],
    )
    run.history.append(tool_turn)

    captured_histories: list[list[Turn]] = []

    class CapturingBackend(LLMBackend):
        model = "fake"

        def complete(
            self,
            *,
            system: str,
            history: list[Turn],
            tools: list[ToolSpec],
            max_tokens: int,
        ) -> LLMResponse:
            captured_histories.append(history)
            return LLMResponse(
                text=json.dumps({"verdicts": []}),
                tool_calls=[],
                usage=Usage(input_tokens=0, output_tokens=0),
            )

    run_verification(brief, run, backend=CapturingBackend(), verify_llm=True)

    assert len(captured_histories) == 1
    # The user turn text should reference the tool content
    user_turn = captured_histories[0][0]
    assert "Apple beats earnings" in user_turn.text or "get_company_news" in user_turn.text
