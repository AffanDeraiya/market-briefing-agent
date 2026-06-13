"""Unit tests for indicators.py — synthetic DataFrames, no network, no fixtures."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.agents.market_brief.utils.indicators import compute_indicators

# ---------------------------------------------------------------------------
# DataFrame builder helpers
# ---------------------------------------------------------------------------


def make_df(
    closes: list[float],
    volumes: list[float] | None = None,
    start: str = "2024-01-02",
) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame with a business-day DatetimeIndex."""
    n = len(closes)
    idx = pd.bdate_range(start=start, periods=n)
    if volumes is None:
        volumes = [1_000_000.0] * n

    opens = [closes[0]] + closes[:-1]  # open = prev close
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]

    return pd.DataFrame(
        {
            "Open": opens,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_empty_df_raises() -> None:
    df: pd.DataFrame = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    with pytest.raises(ValueError, match="empty"):
        compute_indicators(df)


def test_missing_column_raises() -> None:
    df = make_df([100.0, 101.0, 102.0])
    df = df.drop(columns=["Volume"])
    with pytest.raises(ValueError, match="Missing"):
        compute_indicators(df)


# ---------------------------------------------------------------------------
# Max drawdown
# ---------------------------------------------------------------------------


def test_known_drawdown_case() -> None:
    """100 → 120 → 80 → 110: drawdown from 120 to 80 = -33.3%"""
    closes = [100.0, 120.0, 80.0, 110.0]
    df = make_df(closes)
    result = compute_indicators(df)
    dd = result.max_drawdown_pct

    assert dd.value == pytest.approx(-33.3, abs=0.1)
    idx = pd.bdate_range(start="2024-01-02", periods=4)
    assert dd.peak_date == str(idx[1])[:10]  # 120 is at position 1
    assert dd.trough_date == str(idx[2])[:10]  # 80 is at position 2


def test_monotonic_rise_no_drawdown() -> None:
    closes = [100.0, 105.0, 110.0, 115.0, 120.0, 125.0, 130.0, 135.0]
    df = make_df(closes)
    result = compute_indicators(df)
    dd = result.max_drawdown_pct

    assert dd.value == 0.0
    last = pd.bdate_range(start="2024-01-02", periods=8)[-1]
    assert dd.peak_date == str(last)[:10]
    assert dd.trough_date == str(last)[:10]


def test_drawdown_value_negative() -> None:
    closes = [200.0, 150.0, 100.0, 130.0]
    df = make_df(closes)
    result = compute_indicators(df)
    assert result.max_drawdown_pct.value < 0


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------


def test_rsi_overbought_monotonic_rise() -> None:
    """Strongly rising series → RSI ≥ 70 → overbought."""
    # 30 rows of +1% each day — gains dominate heavily
    closes: list[float] = [100.0 * (1.01**i) for i in range(30)]
    df = make_df(closes)
    result = compute_indicators(df)
    assert result.rsi14 >= 70.0
    assert result.rsi_signal == "overbought"


def test_rsi_oversold_monotonic_drop() -> None:
    """Strongly falling series → RSI ≤ 30 → oversold."""
    closes: list[float] = [100.0 * (0.99**i) for i in range(30)]
    df = make_df(closes)
    result = compute_indicators(df)
    assert result.rsi14 <= 30.0
    assert result.rsi_signal == "oversold"


def test_rsi_short_series_returns_neutral() -> None:
    """Fewer than 15 rows → RSI 50.0, neutral."""
    closes = [float(i) for i in range(100, 114)]  # 14 rows
    df = make_df(closes)
    result = compute_indicators(df)
    assert result.rsi14 == pytest.approx(50.0)
    assert result.rsi_signal == "neutral"


def test_rsi_exactly_15_rows() -> None:
    """Exactly 15 rows — RSI should compute (not default to 50)."""
    closes = [float(100 + i) for i in range(15)]
    df = make_df(closes)
    result = compute_indicators(df)
    # Pure gains → RSI should be > 50
    assert result.rsi14 > 50.0


def test_rsi_all_losses_returns_0() -> None:
    """No gains at all → avg_gain = 0, avg_loss > 0 → RSI = 0."""
    closes = [float(100 - i) for i in range(20)]
    df = make_df(closes)
    result = compute_indicators(df)
    assert result.rsi14 == pytest.approx(0.0, abs=0.5)


# ---------------------------------------------------------------------------
# SMA vs price
# ---------------------------------------------------------------------------


def test_sma_vs_price_positive_after_jump() -> None:
    """Price jumps above its own recent history → sma20_vs_price > 0."""
    # Flat at 100 for 25 days, then jump to 120
    closes = [100.0] * 25 + [120.0]
    df = make_df(closes)
    result = compute_indicators(df)
    assert result.sma20_vs_price > 0


def test_sma_vs_price_negative_after_drop() -> None:
    """Price drops below its own recent history → sma20_vs_price < 0."""
    closes = [100.0] * 25 + [80.0]
    df = make_df(closes)
    result = compute_indicators(df)
    assert result.sma20_vs_price < 0


def test_sma_uses_all_rows_when_short() -> None:
    """Fewer rows than window → uses all available rows without error."""
    closes = [100.0, 105.0, 110.0]  # only 3 rows, window 20 & 50
    df = make_df(closes)
    result = compute_indicators(df)
    # sma20 = mean of [100, 105, 110] = 105; latest = 110; (110/105 - 1)*100 ≈ 4.76
    expected = round((110.0 / 105.0 - 1) * 100, 2)
    assert result.sma20_vs_price == pytest.approx(expected, abs=0.01)
    assert result.sma50_vs_price == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# Annualized volatility
# ---------------------------------------------------------------------------


def test_vol_fewer_than_3_rows() -> None:
    closes = [100.0, 102.0]
    df = make_df(closes)
    result = compute_indicators(df)
    assert result.annualized_vol_pct == 0.0


def test_vol_constant_price() -> None:
    closes = [100.0] * 30
    df = make_df(closes)
    result = compute_indicators(df)
    assert result.annualized_vol_pct == 0.0


def test_vol_positive_for_volatile_series() -> None:
    rng = np.random.default_rng(42)
    closes_arr = 100.0 * np.cumprod(1 + rng.normal(0, 0.02, 60))
    closes = closes_arr.tolist()
    df = make_df(closes)
    result = compute_indicators(df)
    assert result.annualized_vol_pct > 0.0


def test_vol_computed_correctly() -> None:
    """Verify the formula matches manual calculation."""
    rng = np.random.default_rng(7)
    closes_arr = 100.0 * np.cumprod(1 + rng.normal(0, 0.01, 40))
    closes = closes_arr.tolist()
    df = make_df(closes)
    s = pd.Series(closes, dtype=float)
    expected = round(float(s.pct_change().dropna().std(ddof=1)) * math.sqrt(252) * 100, 1)
    result = compute_indicators(df)
    assert result.annualized_vol_pct == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# Volume trend
# ---------------------------------------------------------------------------


def _make_volume_df(
    recent_vol: float,
    baseline_vol: float,
    n_recent: int = 10,
    n_baseline: int = 30,
) -> pd.DataFrame:
    total = n_baseline + n_recent
    vols = [baseline_vol] * n_baseline + [recent_vol] * n_recent
    closes = [100.0 + i * 0.1 for i in range(total)]
    return make_df(closes, volumes=vols)


def test_volume_trend_rising() -> None:
    df = _make_volume_df(recent_vol=2_000_000.0, baseline_vol=1_000_000.0)
    result = compute_indicators(df)
    assert result.volume_trend == "rising"


def test_volume_trend_falling() -> None:
    df = _make_volume_df(recent_vol=500_000.0, baseline_vol=1_000_000.0)
    result = compute_indicators(df)
    assert result.volume_trend == "falling"


def test_volume_trend_flat() -> None:
    df = _make_volume_df(recent_vol=1_000_000.0, baseline_vol=1_000_000.0)
    result = compute_indicators(df)
    assert result.volume_trend == "flat"


def test_volume_trend_flat_when_insufficient_prior() -> None:
    """Fewer than 5 prior rows → flat regardless of volumes."""
    closes = [100.0 + i for i in range(14)]
    # Only 4 rows before the last 10
    vols = [100.0] * 4 + [1_000_000.0] * 10
    df = make_df(closes, volumes=vols)
    result = compute_indicators(df)
    assert result.volume_trend == "flat"


def test_volume_trend_flat_zero_baseline() -> None:
    """Zero baseline volume → flat."""
    vols = [0.0] * 30 + [1_000_000.0] * 10
    closes = [100.0 + i for i in range(40)]
    df = make_df(closes, volumes=vols)
    result = compute_indicators(df)
    assert result.volume_trend == "flat"


# ---------------------------------------------------------------------------
# RSI boundary signals
# ---------------------------------------------------------------------------


def test_rsi_signal_boundary_70() -> None:
    """RSI exactly at 70 should be overbought."""
    closes = [float(100 + i * 2) for i in range(30)]
    df = make_df(closes)
    result = compute_indicators(df)
    if result.rsi14 >= 70.0:
        assert result.rsi_signal == "overbought"


def test_rsi_neutral_range() -> None:
    """Alternating up/down → RSI near 50 → neutral."""
    closes_list: list[float] = []
    c = 100.0
    for i in range(40):
        c = c * 1.005 if i % 2 == 0 else c * 0.995
        closes_list.append(c)
    df = make_df(closes_list)
    result = compute_indicators(df)
    assert result.rsi_signal == "neutral"
    assert 30 < result.rsi14 < 70


# ---------------------------------------------------------------------------
# Drawdown peak / trough correctness for extended series
# ---------------------------------------------------------------------------


def test_drawdown_peak_is_before_trough() -> None:
    """Peak date must be <= trough date."""
    closes = [50.0, 80.0, 90.0, 60.0, 70.0, 85.0, 40.0, 55.0]
    df = make_df(closes)
    result = compute_indicators(df)
    dd = result.max_drawdown_pct
    assert dd.peak_date <= dd.trough_date


def test_drawdown_multiple_peaks_picks_latest() -> None:
    """When peak repeats, pick the most-recent occurrence before the trough."""
    closes = [100.0, 100.0, 90.0, 100.0, 80.0, 95.0]
    df = make_df(closes)
    idx = pd.bdate_range(start="2024-01-02", periods=6)
    result = compute_indicators(df)
    dd = result.max_drawdown_pct
    # Trough is the 80 at index 4; running peak at that point is 100 (last at index 3)
    assert dd.trough_date == str(idx[4])[:10]
    assert dd.peak_date == str(idx[3])[:10]
