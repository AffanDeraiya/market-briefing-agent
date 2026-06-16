"""Fully offline tests for the agent loop (agent.py, nodes.py, events.py, cassette.py).

Network calls are prevented by monkeypatching execute_tool in nodes.py.
A FakeBackend replays a pre-built sequence of LLMResponse objects so no real
LLM API key is required.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.agents.market_brief.cassette import CassetteRecorder, hash_history
from src.agents.market_brief.events import (
    CollectingEmitter,
    estimate_cost_usd,
)
from src.agents.market_brief.nodes import strip_code_fences
from src.llm import LLMBackend, LLMResponse, ToolCall, ToolSpec, Turn, Usage
from src.schemas import DISCLAIMER

# ---------------------------------------------------------------------------
# Minimal valid brief JSON (mirrors test_schemas._valid_brief)
# ---------------------------------------------------------------------------

_VALID_BRIEF_DICT: dict[str, Any] = {
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

_VALID_BRIEF_JSON: str = json.dumps(_VALID_BRIEF_DICT)


# ---------------------------------------------------------------------------
# FakeBackend
# ---------------------------------------------------------------------------


class FakeBackend(LLMBackend):
    """Replays a pre-built sequence of LLMResponse objects in order."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.model = "fake-model"
        self._responses = list(responses)
        self._i = 0
        # Capture history passed to each complete() call for introspection
        self.captured_histories: list[list[Turn]] = []

    def complete(
        self,
        *,
        system: str,
        history: list[Turn],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> LLMResponse:
        self.captured_histories.append(list(history))
        if self._i >= len(self._responses):
            raise IndexError(
                f"FakeBackend exhausted: called {self._i + 1} times "
                f"but only {len(self._responses)} responses were provided"
            )
        resp = self._responses[self._i]
        self._i += 1
        return resp


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------

_FAKE_USAGE = Usage(input_tokens=10, output_tokens=5)


def _resp_tool(name: str = "get_price_history", call_id: str = "tc1") -> LLMResponse:
    """An LLMResponse that requests one tool call (is_final=False)."""
    return LLMResponse(
        text="",
        tool_calls=[ToolCall(id=call_id, name=name, input={"ticker": "AAPL", "period": "1y"})],
        usage=_FAKE_USAGE,
    )


def _resp_final(json_text: str = _VALID_BRIEF_JSON) -> LLMResponse:
    """An LLMResponse with final text (no tool calls — is_final=True)."""
    return LLMResponse(text=json_text, tool_calls=[], usage=_FAKE_USAGE)


# ---------------------------------------------------------------------------
# Shared monkeypatch fixture: no network calls from execute_tool
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_execute_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace execute_tool in nodes.py with a canned no-op."""
    monkeypatch.setattr(
        "src.agents.market_brief.nodes.execute_tool",
        lambda name, tool_input, **kwargs: ('{"ok": true}', False),
    )


# ---------------------------------------------------------------------------
# Test 1 — Happy path
# ---------------------------------------------------------------------------


def test_happy_path_one_tool_then_final() -> None:
    """FakeBackend: [tool_call, final_valid_brief] → brief not None, error None."""
    from src.agents.market_brief.agent import run_agent

    backend = FakeBackend([_resp_tool(), _resp_final()])
    emitter = CollectingEmitter()

    result = run_agent("AAPL", "1y", backend=backend, emit=emitter)

    assert result.brief is not None, f"expected a brief, got error={result.error}"
    assert result.error is None

    types = emitter.types()
    assert "run_started" in types
    assert "tool_call" in types
    assert "tool_result" in types
    assert "brief" in types
    assert "usage" in types

    # Sane ordering: run_started is first, usage is last
    assert types[0] == "run_started"
    assert types[-1] == "usage"

    assert result.usage["tool_calls"] == 1
    assert result.usage["iterations"] == 2


# ---------------------------------------------------------------------------
# Test 2 — Repair success
# ---------------------------------------------------------------------------


def test_repair_success() -> None:
    """[tool_call, invalid_json, valid_final] → brief not None, error None, repair_attempted."""
    from src.agents.market_brief.agent import run_agent

    backend = FakeBackend(
        [
            _resp_tool(),
            _resp_final("not json at all"),
            _resp_final(_VALID_BRIEF_JSON),
        ]
    )
    emitter = CollectingEmitter()

    result = run_agent("AAPL", "1y", backend=backend, emit=emitter)

    assert result.brief is not None, f"expected a brief after repair, error={result.error}"
    assert result.error is None

    # A brief event should have been emitted
    assert "brief" in emitter.types()

    # 3 iterations: tool_call, invalid_final, repaired_final
    assert result.usage["iterations"] == 3


# ---------------------------------------------------------------------------
# Test 3 — Repair fail
# ---------------------------------------------------------------------------


def test_repair_fail() -> None:
    """[tool_call, invalid, invalid] → brief None, error[0]=='parse', usage emitted."""
    from src.agents.market_brief.agent import run_agent

    backend = FakeBackend(
        [
            _resp_tool(),
            _resp_final("not json"),
            _resp_final("still not json"),
        ]
    )
    emitter = CollectingEmitter()

    result = run_agent("AAPL", "1y", backend=backend, emit=emitter)

    assert result.brief is None
    assert result.error is not None
    assert result.error[0] == "parse"

    # usage must always be emitted even on failure
    assert "usage" in emitter.types()


# ---------------------------------------------------------------------------
# Test 4 — Tool budget → finalize injection
# ---------------------------------------------------------------------------


def test_tool_budget_finalize_injection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting MAX_TOOL_CALLS=1 forces finalize injection after the first tool batch."""
    from src.agents.market_brief.agent import run_agent

    # Patch the budget constant so the first tool call exhausts the budget
    monkeypatch.setattr("src.agents.market_brief.state.MAX_TOOL_CALLS", 1)

    # We need two tool-call responses so the first batch is processed, then budget hits.
    # After finalize injection the model should produce the final brief.
    backend = FakeBackend(
        [
            _resp_tool(call_id="tc1"),  # 1st LLM call → tool call
            _resp_final(_VALID_BRIEF_JSON),  # 2nd LLM call (after finalize injected) → brief
        ]
    )
    emitter = CollectingEmitter()

    result = run_agent("AAPL", "1y", backend=backend, emit=emitter)

    # The run should complete with a brief
    assert result.brief is not None, (
        f"expected brief after finalize injection, error={result.error}"
    )

    # Verify finalize injection: the second call to complete() should have seen
    # the FINALIZE_NOW_MESSAGE as the last user turn in the history.
    from src.agents.market_brief.prompts import FINALIZE_NOW_MESSAGE

    # backend.captured_histories[1] is the history seen by the 2nd complete() call.
    # The last Turn before the assistant reply should be the finalize message.
    second_call_history = backend.captured_histories[1]
    # Find last user turn
    user_turns = [t for t in second_call_history if t.role == "user"]
    assert user_turns, "no user turns found in second LLM call history"
    assert user_turns[-1].text == FINALIZE_NOW_MESSAGE, (
        f"expected finalize message, got: {user_turns[-1].text!r}"
    )


# ---------------------------------------------------------------------------
# Test 5 — Cassette recording + helpers
# ---------------------------------------------------------------------------


def test_cassette_records_correctly() -> None:
    """Happy path run with a CassetteRecorder → cassette has correct shape."""
    from src.agents.market_brief.agent import run_agent

    backend = FakeBackend([_resp_tool(), _resp_final()])
    recorder = CassetteRecorder({"ticker": "AAPL", "period": "1y"})

    result = run_agent("AAPL", "1y", backend=backend, recorder=recorder)
    assert result.brief is not None

    cassette = recorder.to_dict()
    assert len(cassette["llm_turns"]) == 2
    assert len(cassette["tool_io"]) == 1
    assert cassette["final_brief"] is not None
    assert cassette["usage"] is not None
    assert "input_tokens" in cassette["usage"]


def test_hash_history_deterministic() -> None:
    """Same inputs → same hash; different inputs → different hash."""
    system = "sys"
    history = [Turn(role="user", text="hello")]
    tools: list[ToolSpec] = []

    h1 = hash_history(system, history, tools)
    h2 = hash_history(system, history, tools)
    assert h1 == h2

    history2 = [Turn(role="user", text="different")]
    h3 = hash_history(system, history2, tools)
    assert h1 != h3


def test_strip_code_fences_removes_json_fence() -> None:
    text = '```json\n{"key": "value"}\n```'
    result = strip_code_fences(text)
    assert result == '{"key": "value"}'


def test_strip_code_fences_removes_plain_fence() -> None:
    text = '```\n{"key": 1}\n```'
    result = strip_code_fences(text)
    assert result == '{"key": 1}'


def test_strip_code_fences_no_fence() -> None:
    text = '{"key": "value"}'
    assert strip_code_fences(text) == text


# ---------------------------------------------------------------------------
# Test 6 — estimate_cost_usd
# ---------------------------------------------------------------------------


def test_estimate_cost_gemini_free() -> None:
    assert estimate_cost_usd("gemini-2.5-flash", 1_000_000, 1_000_000) == 0.0


def test_estimate_cost_haiku() -> None:
    # 1M input @ $1/M + 1M output @ $5/M = $6.0
    cost = estimate_cost_usd("claude-haiku-4-5", 1_000_000, 1_000_000)
    assert cost == pytest.approx(6.0, rel=1e-6)


def test_estimate_cost_unknown_model_zero() -> None:
    assert estimate_cost_usd("unknown-model-xyz", 500_000, 500_000) == 0.0


def test_estimate_cost_zero_tokens() -> None:
    assert estimate_cost_usd("claude-haiku-4-5", 0, 0) == 0.0


# ---------------------------------------------------------------------------
# Test 7 — attach_market_data (deterministic enrichment)
# ---------------------------------------------------------------------------


def test_attach_market_data_populates_indicators_and_52w() -> None:
    from src.agents.market_brief.nodes import attach_market_data
    from src.agents.market_brief.state import RunState
    from src.schemas import parse_brief

    brief = parse_brief(_VALID_BRIEF_DICT)
    assert brief.indicators == {}  # optional, empty by default

    state = RunState(ticker="AAPL", period="6mo")
    state.indicators_out = {
        "sma20_vs_price": -4.2,
        "sma50_vs_price": 2.02,
        "rsi14": 44.5,
        "rsi_signal": "neutral",
        "annualized_vol_pct": 23.1,
        "max_drawdown_pct": {"value": -7.8, "peak_date": "2026-06-02", "trough_date": "2026-06-09"},
        "volume_trend": "flat",
    }
    state.price_history_out = {"low_52w": 194.87, "high_52w": 315.20, "latest_close": 291.13}

    attach_market_data(state, brief)

    # indicators flattened (MaxDrawdown -> its value); LLM never owns these
    assert brief.indicators["rsi14"] == 44.5
    assert brief.indicators["rsi_signal"] == "neutral"
    assert brief.indicators["max_drawdown_pct"] == -7.8
    assert brief.indicators["volume_trend"] == "flat"
    # 52-week range merged into snapshot for the range bar
    assert brief.snapshot["low_52w"] == 194.87
    assert brief.snapshot["high_52w"] == 315.20


def test_attach_market_data_noop_without_tool_outputs() -> None:
    from src.agents.market_brief.nodes import attach_market_data
    from src.agents.market_brief.state import RunState
    from src.schemas import parse_brief

    brief = parse_brief(_VALID_BRIEF_DICT)
    state = RunState(ticker="AAPL", period="6mo")

    attach_market_data(state, brief)  # nothing captured -> no change, no crash

    assert brief.indicators == {}
    assert "low_52w" not in brief.snapshot


def test_attach_market_data_price_history_fields() -> None:
    """attach_market_data overwrites price/change/currency from price_history_out."""
    from src.agents.market_brief.nodes import attach_market_data
    from src.agents.market_brief.state import RunState
    from src.schemas import parse_brief

    brief = parse_brief(_VALID_BRIEF_DICT)
    state = RunState(ticker="AAPL", period="6mo")
    state.price_history_out = {
        "latest_close": 191.23,
        "change_pct": {"d1": 1.5, "m1": -3.2, "period": 7.8},
        "currency": "USD",
        "low_52w": 160.0,
        "high_52w": 220.0,
    }

    attach_market_data(state, brief)

    assert brief.snapshot["price"] == 191.23
    assert brief.snapshot["change_1d"] == 1.5
    assert brief.snapshot["change_1m"] == -3.2
    assert brief.snapshot["change_period"] == 7.8
    assert brief.snapshot["currency"] == "USD"
    assert brief.snapshot["low_52w"] == 160.0
    assert brief.snapshot["high_52w"] == 220.0


def test_attach_market_data_fundamentals_fields() -> None:
    """attach_market_data overwrites market_cap/pe/sector from fundamentals_out."""
    from src.agents.market_brief.nodes import attach_market_data
    from src.agents.market_brief.state import RunState
    from src.schemas import parse_brief

    brief = parse_brief(_VALID_BRIEF_DICT)
    state = RunState(ticker="AAPL", period="6mo")
    state.fundamentals_out = {
        "market_cap": 3_000_000_000_000,
        "pe_trailing": 29.5,
        "pe_forward": 25.0,
        "sector": "Technology",
    }

    attach_market_data(state, brief)

    assert brief.snapshot["market_cap"] == 3_000_000_000_000
    assert brief.snapshot["pe"] == 29.5  # trailing preferred over forward
    assert brief.snapshot["sector"] == "Technology"


def test_attach_market_data_fundamentals_pe_forward_fallback() -> None:
    """When pe_trailing is None, pe falls back to pe_forward."""
    from src.agents.market_brief.nodes import attach_market_data
    from src.agents.market_brief.state import RunState
    from src.schemas import parse_brief

    brief = parse_brief(_VALID_BRIEF_DICT)
    state = RunState(ticker="AAPL", period="6mo")
    state.fundamentals_out = {
        "market_cap": None,
        "pe_trailing": None,
        "pe_forward": 22.1,
        "sector": None,
    }

    attach_market_data(state, brief)

    assert brief.snapshot["pe"] == 22.1
    # None market_cap: guard ensures we don't overwrite with None (original value preserved)
    assert brief.snapshot.get("market_cap") == _VALID_BRIEF_DICT["snapshot"]["market_cap"]


def test_post_tool_chart_data_reemit_after_detect_anomalies() -> None:
    """After detect_anomalies, chart_data is re-emitted with full anomaly objects."""
    from src.agents.market_brief.events import CollectingEmitter
    from src.agents.market_brief.nodes import _post_tool_side_effects
    from src.agents.market_brief.state import RunState

    state = RunState(ticker="AAPL", period="3mo")
    # Simulate price history already captured
    state.price_history_out = {
        "week_aggregates": [{"week_start": "2026-01-05", "close": 185.0, "volume": 1000000}],
        "latest_close": 185.0,
    }

    emitter = CollectingEmitter()
    detect_output = json.dumps(
        {
            "anomalies": [
                {
                    "date": "2026-01-10",
                    "kind": "price_spike",
                    "magnitude": "+5.2% (3.1σ)",
                    "severity": "high",
                }
            ],
            "detector_config": {"return_sigma": 2.5, "volume_mult": 3.0, "gap_pct": 4.0},
        }
    )

    _post_tool_side_effects(state, "detect_anomalies", detect_output, False, emitter)

    chart_events = [e for e in emitter.events if e[0] == "chart_data"]
    assert len(chart_events) == 1, "expected one chart_data re-emit after detect_anomalies"
    anomalies = chart_events[0][1]["anomalies"]
    assert len(anomalies) == 1
    assert anomalies[0]["date"] == "2026-01-10"
    assert anomalies[0]["kind"] == "price_spike"
    assert anomalies[0]["magnitude"] == "+5.2% (3.1σ)"
    assert anomalies[0]["severity"] == "high"


def test_post_tool_chart_data_no_reemit_without_price_history() -> None:
    """If price history not yet captured, detect_anomalies does not emit chart_data."""
    from src.agents.market_brief.events import CollectingEmitter
    from src.agents.market_brief.nodes import _post_tool_side_effects
    from src.agents.market_brief.state import RunState

    state = RunState(ticker="AAPL", period="3mo")
    # price_history_out is None — detect_anomalies arrives first

    emitter = CollectingEmitter()
    detect_output = json.dumps(
        {
            "anomalies": [
                {
                    "date": "2026-01-10",
                    "kind": "price_spike",
                    "magnitude": "+5%",
                    "severity": "high",
                }
            ],
            "detector_config": {},
        }
    )

    _post_tool_side_effects(state, "detect_anomalies", detect_output, False, emitter)

    chart_events = [e for e in emitter.events if e[0] == "chart_data"]
    assert len(chart_events) == 0, "should not emit chart_data without price history"


def test_anomaly_focus_enriched_payload() -> None:
    """_maybe_emit_anomaly_focus includes magnitude/severity from anomalies_detail."""
    from src.agents.market_brief.events import CollectingEmitter
    from src.agents.market_brief.nodes import _maybe_emit_anomaly_focus
    from src.agents.market_brief.state import RunState
    from src.llm import ToolCall

    state = RunState(ticker="AAPL", period="3mo")
    state.anomaly_dates = {"2026-01-10": "price_spike"}
    state.anomalies_detail = [
        {
            "date": "2026-01-10",
            "kind": "price_spike",
            "magnitude": "+5.2% (3.1σ)",
            "severity": "high",
        }
    ]

    tc = ToolCall(
        id="tc1",
        name="get_company_news",
        input={"query": "AAPL", "from_date": "2026-01-07", "to_date": "2026-01-13"},
    )

    emitter = CollectingEmitter()
    _maybe_emit_anomaly_focus(state, tc, emitter)

    focus_events = [e for e in emitter.events if e[0] == "anomaly_focus"]
    assert len(focus_events) == 1
    payload = focus_events[0][1]
    assert payload["date"] == "2026-01-10"
    assert payload["kind"] == "price_spike"
    assert payload["magnitude"] == "+5.2% (3.1σ)"
    assert payload["severity"] == "high"


def test_anomaly_focus_no_detail_emits_date_kind_only() -> None:
    """_maybe_emit_anomaly_focus emits only date+kind when detail not found."""
    from src.agents.market_brief.events import CollectingEmitter
    from src.agents.market_brief.nodes import _maybe_emit_anomaly_focus
    from src.agents.market_brief.state import RunState
    from src.llm import ToolCall

    state = RunState(ticker="AAPL", period="3mo")
    state.anomaly_dates = {"2026-01-10": "price_drop"}
    # No anomalies_detail populated yet

    tc = ToolCall(
        id="tc1",
        name="get_company_news",
        input={"query": "AAPL", "from_date": "2026-01-08", "to_date": "2026-01-12"},
    )

    emitter = CollectingEmitter()
    _maybe_emit_anomaly_focus(state, tc, emitter)

    focus_events = [e for e in emitter.events if e[0] == "anomaly_focus"]
    assert len(focus_events) == 1
    payload = focus_events[0][1]
    assert payload["date"] == "2026-01-10"
    assert payload["kind"] == "price_drop"
    # magnitude/severity not present when detail is missing
    assert "magnitude" not in payload
    assert "severity" not in payload
