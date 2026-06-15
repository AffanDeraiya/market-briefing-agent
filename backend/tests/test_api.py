"""Offline tests for the FastAPI layer (no network, no real LLM)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.agents.market_brief.utils.market_data import (
    Fundamentals,
    TickerNotFoundError,
)
from src.api.guards import daily_counter, inflight
from src.main import create_app

# ---------------------------------------------------------------------------
# Fake agent helpers
# ---------------------------------------------------------------------------


class _FakeBackend:
    model: str = "fake-model"


def _fake_run_agent(
    ticker: str,
    period: str,
    *,
    backend: Any,
    emit: Any = None,
    recorder: Any = None,
    today: Any = None,
) -> MagicMock:
    if emit is not None:
        emit("run_started", {"ticker": ticker, "period": period, "run_id": "test-run"})
        emit("tool_call", {"seq": 1, "name": "market_data", "input": {}})
        emit("brief", {"ticker": ticker, "summary": "test brief"})
        emit("usage", {"input_tokens": 10, "output_tokens": 20})
    result = MagicMock()
    result.error = None
    result.usage = {"input_tokens": 10, "output_tokens": 20}
    # result.brief is an auto-attribute truthy MagicMock → produced=True → no refund
    return result


def _fake_run_agent_error(
    ticker: str,
    period: str,
    *,
    backend: Any,
    emit: Any = None,
    recorder: Any = None,
    today: Any = None,
) -> MagicMock:
    """Fake run_agent that emits an error event and returns a result with no brief."""
    if emit is not None:
        emit(
            "error",
            {"kind": "internal", "message": "An internal error occurred. Please try again."},
        )
        emit("usage", {"input_tokens": 0, "output_tokens": 0})
    result = MagicMock()
    result.error = ("internal", "boom")
    result.brief = None  # explicitly None → produced=False → refund fires
    result.usage = {"input_tokens": 0, "output_tokens": 0}
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Fresh app + reset per-IP and global counters for each test."""
    monkeypatch.setattr("src.api.sse.get_backend", lambda: _FakeBackend())
    monkeypatch.setattr("src.api.sse.run_agent", _fake_run_agent)

    app = create_app()
    daily_counter.reset()
    inflight.reset()
    app.state.limiter.reset()
    return TestClient(app)


# ---------------------------------------------------------------------------
# Existing tests (kept intact)
# ---------------------------------------------------------------------------


def test_validate_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/validate/<ticker> returns valid=True with name/exchange when yfinance succeeds."""
    fake_fund = Fundamentals(
        name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        industry="Consumer Electronics",
        market_cap=3_000_000_000_000,
        pe_trailing=30.0,
        pe_forward=28.0,
        dividend_yield=0.005,
        next_earnings_date=None,
        beta=1.2,
    )
    monkeypatch.setattr("src.api.routes.get_fundamentals", lambda t: fake_fund)

    resp = client.get("/api/validate/AAPL")
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["ticker"] == "AAPL"
    assert body["name"] == "Apple Inc."
    assert body["exchange"] == "NASDAQ"


def test_validate_not_found(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/validate/<ticker> returns valid=False when TickerNotFoundError is raised."""
    monkeypatch.setattr(
        "src.api.routes.get_fundamentals",
        lambda t: (_ for _ in ()).throw(TickerNotFoundError("not found")),
    )

    resp = client.get("/api/validate/ZZZZ")
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["name"] is None
    assert body["exchange"] is None


def test_validate_bad_format(client: TestClient) -> None:
    """GET /api/validate/<ticker> returns 400 for invalid ticker format."""
    resp = client.get("/api/validate/!!!")
    assert resp.status_code == 400


def test_brief_sse_happy_path(client: TestClient) -> None:
    """POST /api/brief streams SSE events including run_started, tool_call, brief, usage."""
    with client.stream("POST", "/api/brief", json={"ticker": "AAPL", "period": "3mo"}) as r:
        assert r.status_code == 200
        lines = list(r.iter_lines())

    event_types = [line.removeprefix("event: ") for line in lines if line.startswith("event: ")]
    assert "run_started" in event_types
    assert "tool_call" in event_types
    assert "brief" in event_types
    assert "usage" in event_types


def test_brief_bad_ticker(client: TestClient) -> None:
    """POST /api/brief returns 400 for an invalid ticker."""
    resp = client.post("/api/brief", json={"ticker": "!!", "period": "3mo"})
    assert resp.status_code == 400


def test_global_daily_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Third POST /api/brief returns 429 budget error when GLOBAL_DAILY_BRIEFS=2."""
    monkeypatch.setenv("GLOBAL_DAILY_BRIEFS", "2")
    monkeypatch.setattr("src.api.sse.get_backend", lambda: _FakeBackend())
    monkeypatch.setattr("src.api.sse.run_agent", _fake_run_agent)

    app = create_app()
    daily_counter.reset()
    inflight.reset()
    app.state.limiter.reset()
    c = TestClient(app)

    # First two requests must succeed — drain the streams so the connection closes cleanly.
    for _ in range(2):
        with c.stream("POST", "/api/brief", json={"ticker": "AAPL", "period": "3mo"}) as r:
            assert r.status_code == 200
            # consume fully
            for _ in r.iter_bytes():
                pass

    # Third must hit the global cap
    resp = c.post("/api/brief", json={"ticker": "AAPL", "period": "3mo"})
    assert resp.status_code == 429
    body = resp.json()
    assert body["detail"]["kind"] == "budget"


def test_per_ip_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Third POST /api/brief returns 429 rate_limit error when RATE_LIMIT_BRIEFS_PER_HOUR=2."""
    monkeypatch.setenv("RATE_LIMIT_BRIEFS_PER_HOUR", "2")
    monkeypatch.setenv("GLOBAL_DAILY_BRIEFS", "1000")
    monkeypatch.setattr("src.api.sse.get_backend", lambda: _FakeBackend())
    monkeypatch.setattr("src.api.sse.run_agent", _fake_run_agent)

    app = create_app()
    daily_counter.reset()
    inflight.reset()
    app.state.limiter.reset()
    c = TestClient(app)

    # First two succeed — consume the streams fully before the next call.
    for _ in range(2):
        with c.stream("POST", "/api/brief", json={"ticker": "AAPL", "period": "3mo"}) as r:
            assert r.status_code == 200
            for _ in r.iter_bytes():
                pass

    # Third must hit the per-IP cap
    resp = c.post("/api/brief", json={"ticker": "AAPL", "period": "3mo"})
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"]["kind"] == "rate_limit"


def test_health(client: TestClient) -> None:
    """GET /api/health returns status ok and daily_briefs_remaining as int."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["daily_briefs_remaining"], int)


# ---------------------------------------------------------------------------
# Fix #2 — Global daily cap: refund on failure
# ---------------------------------------------------------------------------


def test_daily_counter_refund() -> None:
    """Consuming then refunding returns remaining() to the cap (unit test for DailyCounter)."""
    daily_counter.reset()
    cap = daily_counter.remaining()
    assert daily_counter.try_consume()
    assert daily_counter.remaining() == cap - 1
    daily_counter.refund()
    assert daily_counter.remaining() == cap


def test_daily_refund_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Daily slot is refunded when run_agent returns a result with brief=None (error path)."""
    monkeypatch.setenv("GLOBAL_DAILY_BRIEFS", "5")
    monkeypatch.setattr("src.api.sse.get_backend", lambda: _FakeBackend())
    monkeypatch.setattr("src.api.sse.run_agent", _fake_run_agent_error)

    app = create_app()
    daily_counter.reset()
    inflight.reset()
    app.state.limiter.reset()
    c = TestClient(app)

    cap = daily_counter.remaining()  # should be 5

    # POST once — the agent errors (brief=None) so the slot must be refunded.
    with c.stream("POST", "/api/brief", json={"ticker": "AAPL", "period": "3mo"}) as r:
        assert r.status_code == 200
        for _ in r.iter_bytes():
            pass

    # Remaining should be back to the original cap after the refund.
    assert daily_counter.remaining() == cap


# ---------------------------------------------------------------------------
# Fix #2 — Per-IP daily cap
# ---------------------------------------------------------------------------


def test_per_ip_daily_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Third POST /api/brief returns 429 rate_limit when RATE_LIMIT_BRIEFS_PER_DAY=2."""
    monkeypatch.setenv("RATE_LIMIT_BRIEFS_PER_DAY", "2")
    monkeypatch.setenv("RATE_LIMIT_BRIEFS_PER_HOUR", "1000")
    monkeypatch.setenv("GLOBAL_DAILY_BRIEFS", "1000")
    monkeypatch.setattr("src.api.sse.get_backend", lambda: _FakeBackend())
    monkeypatch.setattr("src.api.sse.run_agent", _fake_run_agent)

    app = create_app()
    daily_counter.reset()
    inflight.reset()
    app.state.limiter.reset()
    c = TestClient(app)

    # First two must succeed.
    for _ in range(2):
        with c.stream("POST", "/api/brief", json={"ticker": "AAPL", "period": "3mo"}) as r:
            assert r.status_code == 200
            for _ in r.iter_bytes():
                pass

    # Third must be rejected by the per-IP daily cap (slowapi → rate_limit handler).
    resp = c.post("/api/brief", json={"ticker": "AAPL", "period": "3mo"})
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"]["kind"] == "rate_limit"


# ---------------------------------------------------------------------------
# Fix #3 — Throttle /api/validate
# ---------------------------------------------------------------------------


def test_validate_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Third GET /api/validate returns 429 when RATE_LIMIT_VALIDATE_PER_HOUR=2."""
    monkeypatch.setenv("RATE_LIMIT_VALIDATE_PER_HOUR", "2")
    fake_fund = Fundamentals(
        name="Apple Inc.",
        exchange="NASDAQ",
        sector=None,
        industry=None,
        market_cap=None,
        pe_trailing=None,
        pe_forward=None,
        dividend_yield=None,
        next_earnings_date=None,
        beta=None,
    )
    monkeypatch.setattr("src.api.routes.get_fundamentals", lambda t: fake_fund)
    monkeypatch.setattr("src.api.sse.get_backend", lambda: _FakeBackend())
    monkeypatch.setattr("src.api.sse.run_agent", _fake_run_agent)

    app = create_app()
    daily_counter.reset()
    inflight.reset()
    app.state.limiter.reset()
    c = TestClient(app)

    assert c.get("/api/validate/AAPL").status_code == 200
    assert c.get("/api/validate/AAPL").status_code == 200
    # Third request must be throttled.
    assert c.get("/api/validate/AAPL").status_code == 429


# ---------------------------------------------------------------------------
# Fix #6 — InFlightTracker unit tests
# ---------------------------------------------------------------------------


def test_inflight_global_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """InFlightTracker respects MAX_CONCURRENT_GLOBAL."""
    monkeypatch.setenv("MAX_CONCURRENT_GLOBAL", "2")
    monkeypatch.setenv("MAX_CONCURRENT_PER_IP", "100")
    inflight.reset()

    assert inflight.try_acquire("1.2.3.4") is True
    assert inflight.try_acquire("5.6.7.8") is True
    # Global cap of 2 reached — different IP but still rejected.
    assert inflight.try_acquire("9.10.11.12") is False


def test_inflight_per_ip_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """InFlightTracker respects MAX_CONCURRENT_PER_IP."""
    monkeypatch.setenv("MAX_CONCURRENT_GLOBAL", "100")
    monkeypatch.setenv("MAX_CONCURRENT_PER_IP", "1")
    inflight.reset()

    assert inflight.try_acquire("1.2.3.4") is True
    # Same IP already at cap.
    assert inflight.try_acquire("1.2.3.4") is False
    # Different IP is fine.
    assert inflight.try_acquire("5.6.7.8") is True


def test_inflight_release(monkeypatch: pytest.MonkeyPatch) -> None:
    """Releasing a slot allows the next acquire to succeed."""
    monkeypatch.setenv("MAX_CONCURRENT_GLOBAL", "1")
    monkeypatch.setenv("MAX_CONCURRENT_PER_IP", "1")
    inflight.reset()

    assert inflight.try_acquire("1.2.3.4") is True
    assert inflight.try_acquire("1.2.3.4") is False  # both global and per-IP full

    inflight.release("1.2.3.4")

    # After release the slot is free again.
    assert inflight.try_acquire("1.2.3.4") is True


# ---------------------------------------------------------------------------
# Fix #9 — Security headers
# ---------------------------------------------------------------------------


def test_security_headers_present(client: TestClient) -> None:
    """Every response carries the required security headers."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert "max-age=63072000" in resp.headers["Strict-Transport-Security"]
    assert "geolocation=()" in resp.headers["Permissions-Policy"]
