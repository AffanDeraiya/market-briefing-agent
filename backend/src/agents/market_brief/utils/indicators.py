"""Pure-function technical indicators — no I/O, no network, no LLM."""

from __future__ import annotations

import math
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel

_REQUIRED_COLS = {"Open", "High", "Low", "Close", "Volume"}


def _validate(df: pd.DataFrame) -> None:
    if df.empty:
        raise ValueError("DataFrame is empty")
    missing = _REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class MaxDrawdown(BaseModel):
    value: float  # negative percent, e.g. -33.3; 0.0 if no drawdown
    peak_date: str  # ISO YYYY-MM-DD
    trough_date: str  # ISO YYYY-MM-DD


class Indicators(BaseModel):
    sma20_vs_price: float  # percent above(+)/below(-) SMA20, round 2
    sma50_vs_price: float  # same vs SMA50
    rsi14: float  # round 1
    rsi_signal: Literal["overbought", "oversold", "neutral"]
    annualized_vol_pct: float  # round 1
    max_drawdown_pct: MaxDrawdown
    volume_trend: Literal["rising", "falling", "flat"]


# ---------------------------------------------------------------------------
# Helper computations
# ---------------------------------------------------------------------------


def _sma_vs_price(close: pd.Series[Any], window: int) -> float:
    n = min(window, len(close))
    sma = float(close.iloc[-n:].mean())
    latest = float(close.iloc[-1])
    return round((latest / sma - 1) * 100, 2)


def _rsi14(close: pd.Series[Any]) -> float:
    if len(close) < 15:
        return 50.0
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    avg_gain = gains.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    last_gain = float(avg_gain.iloc[-1])
    last_loss = float(avg_loss.iloc[-1])
    if math.isnan(last_gain) or math.isnan(last_loss):
        return 50.0
    if last_gain == 0 and last_loss == 0:
        return 50.0
    if last_loss == 0:
        return 100.0
    rs = last_gain / last_loss
    return round(100 - 100 / (1 + rs), 1)


def _rsi_signal(rsi: float) -> Literal["overbought", "oversold", "neutral"]:
    if rsi >= 70:
        return "overbought"
    if rsi <= 30:
        return "oversold"
    return "neutral"


def _annualized_vol(close: pd.Series[Any]) -> float:
    if len(close) < 3:
        return 0.0
    ret = close.pct_change().dropna()
    if len(ret) == 0:
        return 0.0
    return round(float(ret.std(ddof=1)) * math.sqrt(252) * 100, 1)


def _max_drawdown(close: pd.Series[Any]) -> MaxDrawdown:
    running_peak = close.cummax()
    drawdown = close / running_peak - 1

    min_dd = float(drawdown.min())

    last_date = str(close.index[-1])[:10]

    if min_dd >= 0:
        # Monotonic rise — no drawdown
        return MaxDrawdown(value=0.0, peak_date=last_date, trough_date=last_date)

    trough_idx = int(drawdown.argmin())
    trough_date = str(close.index[trough_idx])[:10]

    # peak is the most recent date <= trough where close == running_peak at trough
    peak_val = float(running_peak.iloc[trough_idx])
    candidates = close.iloc[: trough_idx + 1]
    # find last index where close == peak_val
    matches = candidates[candidates == peak_val]
    peak_date = str(close.index[0])[:10] if matches.empty else str(matches.index[-1])[:10]

    value = round(min_dd * 100, 1)
    return MaxDrawdown(value=value, peak_date=peak_date, trough_date=trough_date)


def _volume_trend(
    volume: pd.Series[Any],
) -> Literal["rising", "falling", "flat"]:
    n = len(volume)
    recent_n = 10
    baseline_n = 30

    recent = volume.iloc[max(0, n - recent_n) :]
    prior = volume.iloc[max(0, n - recent_n - baseline_n) : max(0, n - recent_n)]

    if len(prior) < 5:
        return "flat"

    baseline = float(prior.mean())
    if baseline == 0:
        return "flat"

    ratio = float(recent.mean()) / baseline
    if ratio > 1.15:
        return "rising"
    if ratio < 0.85:
        return "falling"
    return "flat"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_indicators(df: pd.DataFrame) -> Indicators:
    """Compute technical indicators for a validated OHLCV DataFrame."""
    _validate(df)

    close = df["Close"].astype(float)
    volume = df["Volume"].astype(float)

    rsi = _rsi14(close)

    return Indicators(
        sma20_vs_price=_sma_vs_price(close, 20),
        sma50_vs_price=_sma_vs_price(close, 50),
        rsi14=rsi,
        rsi_signal=_rsi_signal(rsi),
        annualized_vol_pct=_annualized_vol(close),
        max_drawdown_pct=_max_drawdown(close),
        volume_trend=_volume_trend(volume),
    )


__all__ = ["Indicators", "MaxDrawdown", "compute_indicators"]
