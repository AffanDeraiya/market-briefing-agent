"""Cache behavior and adapter error paths — fully offline (yfinance monkeypatched)."""

import os
import time
from typing import Any

import pandas as pd
import pytest

from src.agents.market_brief.utils import market_data


def _ohlcv(closes: list[float], volume: int = 1_000_000) -> pd.DataFrame:
    idx = pd.bdate_range("2026-01-05", periods=len(closes))
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c * 1.01 for c in closes],
            "Low": [c * 0.99 for c in closes],
            "Close": closes,
            "Volume": [volume] * len(closes),
        },
        index=idx,
    )


class FakeTicker:
    """Stands in for yf.Ticker; counts network-ish calls."""

    history_calls = 0
    frame: pd.DataFrame = _ohlcv([100.0, 102.0, 101.0])
    info_dict: dict[str, Any] = {"currency": "USD", "shortName": "Fake Inc."}

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker

    def history(self, **_: Any) -> pd.DataFrame:
        FakeTicker.history_calls += 1
        return FakeTicker.frame.copy()

    @property
    def info(self) -> dict[str, Any]:
        return FakeTicker.info_dict


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MBA_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("src.agents.market_brief.utils.market_data.yf.Ticker", FakeTicker)
    FakeTicker.history_calls = 0
    FakeTicker.frame = _ohlcv([100.0, 102.0, 101.0])
    FakeTicker.info_dict = {"currency": "USD", "shortName": "Fake Inc."}


def test_fetch_ohlcv_uses_cache_on_second_call() -> None:
    df1 = market_data.fetch_ohlcv("AAPL", "1mo")
    df2 = market_data.fetch_ohlcv("AAPL", "1mo")
    assert FakeTicker.history_calls == 1
    pd.testing.assert_frame_equal(df1, df2, check_freq=False)


def test_fetch_ohlcv_refetches_when_cache_stale() -> None:
    market_data.fetch_ohlcv("AAPL", "1mo")
    cached = market_data.cache_dir() / "AAPL_1mo.parquet"
    stale = time.time() - 25 * 3600
    os.utime(cached, (stale, stale))
    market_data.fetch_ohlcv("AAPL", "1mo")
    assert FakeTicker.history_calls == 2


def test_fetch_ohlcv_unknown_ticker_raises() -> None:
    FakeTicker.frame = pd.DataFrame()
    with pytest.raises(market_data.TickerNotFoundError):
        market_data.fetch_ohlcv("NOPE", "1mo")


def test_price_history_compact_shape() -> None:
    closes = [100.0 + i for i in range(30)]
    FakeTicker.frame = _ohlcv(closes)
    out = market_data.get_price_history("AAPL", "3mo")
    assert out.latest_close == 129.0
    assert out.currency == "USD"
    assert out.change_pct.period == pytest.approx(29.0, abs=0.01)
    assert 1 <= len(out.notable_days) <= 5
    assert len(out.week_aggregates) >= 4
    # compactness: summaries only, never one entry per trading day
    assert len(out.week_aggregates) < len(closes)


def test_fundamentals_nulls_never_invented() -> None:
    FakeTicker.info_dict = {"shortName": "Fake Inc."}
    out = market_data.get_fundamentals("AAPL")
    assert out.name == "Fake Inc."
    assert out.pe_trailing is None
    assert out.market_cap is None
    assert out.next_earnings_date is None
