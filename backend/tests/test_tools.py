"""Offline tests for tools.py and the RunState additions to state.py."""

from __future__ import annotations

import json
import time
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.agents.market_brief import tools as tools_mod
from src.agents.market_brief.state import (
    MAX_ITERATIONS,
    MAX_TOOL_CALLS,
    RUN_TIMEOUT_S,
    RunState,
)
from src.agents.market_brief.tools import TOOLS, execute_tool, tool_specs

# ---------------------------------------------------------------------------
# tool_specs() shape tests
# ---------------------------------------------------------------------------


EXPECTED_TOOL_NAMES = {
    "get_price_history",
    "get_fundamentals",
    "compute_indicators",
    "detect_anomalies",
    "get_company_news",
    "search_web",
    "fetch_page",
}


def test_tool_specs_returns_seven() -> None:
    specs = tool_specs()
    assert len(specs) == 7


def test_tool_specs_names_are_exact() -> None:
    names = {s.name for s in tool_specs()}
    assert names == EXPECTED_TOOL_NAMES


def test_tool_specs_additional_properties_false() -> None:
    for spec in tool_specs():
        assert spec.input_schema.get("additionalProperties") is False, (
            f"{spec.name}: additionalProperties must be False"
        )


def test_tool_specs_have_required_list() -> None:
    for spec in tool_specs():
        assert "required" in spec.input_schema, f"{spec.name}: missing 'required'"
        assert isinstance(spec.input_schema["required"], list)


def test_tools_dict_matches_specs() -> None:
    assert set(TOOLS.keys()) == EXPECTED_TOOL_NAMES


# ---------------------------------------------------------------------------
# execute_tool — happy path
# ---------------------------------------------------------------------------


def test_execute_tool_get_fundamentals_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_result = '{"name":"Apple Inc.","exchange":"NASDAQ"}'
    fake_obj = MagicMock()
    fake_obj.model_dump_json.return_value = fake_result

    monkeypatch.setattr(tools_mod, "get_fundamentals", lambda ticker: fake_obj)

    content, is_error = execute_tool("get_fundamentals", {"ticker": "AAPL"})
    assert is_error is False
    assert content == fake_result


def test_execute_tool_get_price_history_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_result = '{"latest_close":150.0}'
    fake_obj = MagicMock()
    fake_obj.model_dump_json.return_value = fake_result

    monkeypatch.setattr(tools_mod, "get_price_history", lambda ticker, period: fake_obj)

    content, is_error = execute_tool("get_price_history", {"ticker": "AAPL", "period": "1mo"})
    assert is_error is False
    assert content == fake_result


# ---------------------------------------------------------------------------
# execute_tool — unknown tool
# ---------------------------------------------------------------------------


def test_execute_tool_unknown_name_returns_error() -> None:
    content, is_error = execute_tool("nonexistent_tool", {})
    assert is_error is True
    data = json.loads(content)
    assert "error" in data
    assert "nonexistent_tool" in data["error"]


# ---------------------------------------------------------------------------
# execute_tool — handler exception propagates as error
# ---------------------------------------------------------------------------


def test_execute_tool_handler_exception_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_ticker: str) -> Any:
        raise ValueError("boom")

    monkeypatch.setattr(tools_mod, "get_fundamentals", _boom)

    content, is_error = execute_tool("get_fundamentals", {"ticker": "AAPL"})
    assert is_error is True
    data = json.loads(content)
    assert "boom" in data["error"]


def test_execute_tool_ticker_not_found_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.agents.market_brief.utils.market_data import TickerNotFoundError

    def _raise(_ticker: str) -> Any:
        raise TickerNotFoundError("no data for NOPE")

    monkeypatch.setattr(tools_mod, "get_fundamentals", _raise)

    content, is_error = execute_tool("get_fundamentals", {"ticker": "NOPE"})
    assert is_error is True
    assert "no data for NOPE" in json.loads(content)["error"]


# ---------------------------------------------------------------------------
# execute_tool — date parsing for get_company_news
# ---------------------------------------------------------------------------


def test_get_company_news_date_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify ISO date strings are converted to date objects before calling the util."""
    captured: dict[str, Any] = {}
    fake_obj = MagicMock()
    fake_obj.model_dump_json.return_value = '{"results":[]}'

    def _fake_get_company_news(
        query: str,
        from_date: date | None,
        to_date: date | None,
        max_results: int,
    ) -> Any:
        captured["from_date"] = from_date
        captured["to_date"] = to_date
        return fake_obj

    monkeypatch.setattr(tools_mod, "get_company_news", _fake_get_company_news)

    execute_tool(
        "get_company_news",
        {"query": "q", "from_date": "2026-01-01", "to_date": "2026-01-05"},
    )

    assert captured["from_date"] == date(2026, 1, 1)
    assert captured["to_date"] == date(2026, 1, 5)


def test_get_company_news_missing_dates_pass_none(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    fake_obj = MagicMock()
    fake_obj.model_dump_json.return_value = '{"results":[]}'

    def _fake_get_company_news(
        query: str,
        from_date: date | None,
        to_date: date | None,
        max_results: int,
    ) -> Any:
        captured["from_date"] = from_date
        captured["to_date"] = to_date
        return fake_obj

    monkeypatch.setattr(tools_mod, "get_company_news", _fake_get_company_news)

    execute_tool("get_company_news", {"query": "q"})

    assert captured["from_date"] is None
    assert captured["to_date"] is None


def test_get_company_news_empty_string_dates_pass_none(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    fake_obj = MagicMock()
    fake_obj.model_dump_json.return_value = '{"results":[]}'

    def _fake_get_company_news(
        query: str,
        from_date: date | None,
        to_date: date | None,
        max_results: int,
    ) -> Any:
        captured["from_date"] = from_date
        captured["to_date"] = to_date
        return fake_obj

    monkeypatch.setattr(tools_mod, "get_company_news", _fake_get_company_news)

    execute_tool("get_company_news", {"query": "q", "from_date": "", "to_date": ""})

    assert captured["from_date"] is None
    assert captured["to_date"] is None


# ---------------------------------------------------------------------------
# execute_tool — timeout
# ---------------------------------------------------------------------------


def test_execute_tool_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Handler that sleeps longer than timeout_s → is_error True, 'timed out' in message."""

    def _slow(_ticker: str) -> Any:
        time.sleep(2)
        return "{}"

    monkeypatch.setattr(tools_mod, "get_fundamentals", _slow)

    content, is_error = execute_tool("get_fundamentals", {"ticker": "AAPL"}, timeout_s=0.2)
    assert is_error is True
    data = json.loads(content)
    assert "timed out" in data["error"]


# ---------------------------------------------------------------------------
# RunState tests
# ---------------------------------------------------------------------------


def test_run_state_no_budget_issue_initially() -> None:
    state = RunState(ticker="AAPL", period="1mo")
    assert state.budget_reason() is None
    assert not state.tool_budget_exceeded()
    assert not state.iteration_budget_exceeded()
    assert not state.timed_out()


def test_run_state_tool_budget_exceeded() -> None:
    state = RunState(ticker="AAPL", period="1mo", tool_calls_made=MAX_TOOL_CALLS)
    assert state.tool_budget_exceeded()
    assert state.budget_reason() == "tool budget"


def test_run_state_iteration_budget_exceeded() -> None:
    state = RunState(ticker="AAPL", period="1mo", iterations=MAX_ITERATIONS)
    assert state.iteration_budget_exceeded()
    # tool budget takes precedence only if tool_calls_made is also at max; here it isn't
    assert state.budget_reason() == "iteration budget"


def test_run_state_tool_budget_takes_precedence() -> None:
    state = RunState(
        ticker="AAPL",
        period="1mo",
        tool_calls_made=MAX_TOOL_CALLS,
        iterations=MAX_ITERATIONS,
    )
    assert state.budget_reason() == "tool budget"


def test_run_state_timed_out() -> None:
    # Force started_at to a time far in the past so elapsed > RUN_TIMEOUT_S
    past = time.monotonic() - (RUN_TIMEOUT_S + 10)
    state = RunState(ticker="AAPL", period="1mo", started_at=past)
    assert state.timed_out()
    assert state.budget_reason() == "run timeout"


def test_run_state_elapsed_increases() -> None:
    state = RunState(ticker="AAPL", period="1mo")
    t1 = state.elapsed_s()
    time.sleep(0.05)
    t2 = state.elapsed_s()
    assert t2 > t1


def test_run_state_default_period_variants() -> None:
    for period in ("1mo", "3mo", "6mo", "1y"):
        s = RunState(ticker="TEST", period=period)
        assert s.period == period


def test_run_state_anomaly_dates_default_empty() -> None:
    state = RunState(ticker="AAPL", period="3mo")
    assert state.anomaly_dates == {}


def test_run_state_history_default_empty() -> None:
    state = RunState(ticker="AAPL", period="1mo")
    assert state.history == []
