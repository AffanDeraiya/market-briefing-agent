"""Unit tests for src.agents.market_brief.utils.symbols (no network)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from src.agents.market_brief.utils.symbols import SymbolSuggestion, search_symbols

# ---------------------------------------------------------------------------
# Minimal fake httpx response
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal stand-in for httpx.Response used in monkeypatched tests."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:  # noqa: D401
        """No-op — simulates a 200 OK response."""

    def json(self) -> dict[str, Any]:
        return self._payload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_search_symbols_filters_allowed_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only quotes with an allowed quoteType are included in the output."""
    fake_payload = {
        "quotes": [
            {
                "symbol": "AAPL",
                "quoteType": "EQUITY",
                "shortname": "Apple Inc.",
                "exchDisp": "NASDAQ",
            },
            {
                "symbol": "AAPLOPT",
                "quoteType": "OPTION",  # not in _ALLOWED_TYPES — must be dropped
                "shortname": "Apple Call Option",
                "exchDisp": "CBOE",
            },
        ]
    }

    monkeypatch.setattr(
        "src.agents.market_brief.utils.symbols.httpx.get",
        lambda *args, **kwargs: _FakeResponse(fake_payload),
    )

    results = search_symbols("apple")

    assert len(results) == 1
    assert results[0] == SymbolSuggestion(symbol="AAPL", name="Apple Inc.", exchange="NASDAQ")


def test_search_symbols_http_error_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An httpx.HTTPError from the upstream call returns an empty list (never raises)."""

    def _raise(*args: Any, **kwargs: Any) -> None:
        raise httpx.RequestError("connection refused")

    monkeypatch.setattr(
        "src.agents.market_brief.utils.symbols.httpx.get",
        _raise,
    )

    results = search_symbols("aapl")
    assert results == []


def test_search_symbols_too_long_query_skips_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A query longer than 32 characters returns [] without calling httpx.get."""
    called: list[bool] = []

    def _should_not_be_called(*args: Any, **kwargs: Any) -> _FakeResponse:
        called.append(True)
        return _FakeResponse({"quotes": []})

    monkeypatch.setattr(
        "src.agents.market_brief.utils.symbols.httpx.get",
        _should_not_be_called,
    )

    long_query = "A" * 33  # 33 chars — one over the 32-char cap
    results = search_symbols(long_query)

    assert results == []
    assert called == [], "httpx.get must not be called for an over-length query"
