"""Pure-function anomaly detector for OHLCV DataFrames — no I/O, no network, no LLM."""

from __future__ import annotations

import math
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel

from ..state import GAP_PCT, MAX_ANOMALIES, RETURN_SIGMA, VOLUME_MULT

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


class DetectorConfig(BaseModel):
    return_sigma: float = RETURN_SIGMA
    volume_mult: float = VOLUME_MULT
    gap_pct: float = GAP_PCT


class AnomalyEvent(BaseModel):
    date: str  # ISO YYYY-MM-DD
    kind: Literal["price_spike", "price_drop", "volume_surge", "gap"]
    magnitude: str
    severity: Literal["high", "medium"]


class AnomalyReport(BaseModel):
    anomalies: list[AnomalyEvent]
    detector_config: DetectorConfig


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def _detect_price_events(
    close: pd.Series[Any],
    config: DetectorConfig,
) -> list[AnomalyEvent]:
    ret = close.pct_change()
    sigma = float(ret.std(ddof=1))
    if math.isnan(sigma) or sigma == 0:
        return []

    events: list[AnomalyEvent] = []
    threshold = config.return_sigma * sigma

    for idx in ret.index:
        r = ret.loc[idx]
        if not isinstance(r, float):
            r = float(r)
        if math.isnan(r):
            continue
        if abs(r) > threshold:
            kind: Literal["price_spike", "price_drop"] = "price_spike" if r > 0 else "price_drop"
            sigma_mult = abs(r) / sigma
            magnitude = f"{r * 100:+.1f}% ({sigma_mult:.1f}σ)"
            severity: Literal["high", "medium"] = "high" if abs(r) >= 3.5 * sigma else "medium"
            events.append(
                AnomalyEvent(
                    date=str(idx)[:10],
                    kind=kind,
                    magnitude=magnitude,
                    severity=severity,
                )
            )
    return events


def _detect_volume_events(
    volume: pd.Series[Any],
    config: DetectorConfig,
) -> list[AnomalyEvent]:
    avg30 = volume.shift(1).rolling(30, min_periods=5).mean()

    events: list[AnomalyEvent] = []
    for idx in volume.index:
        avg = avg30.loc[idx]
        if not isinstance(avg, float):
            avg = float(avg)
        if math.isnan(avg) or avg <= 0:
            continue
        vol = volume.loc[idx]
        if not isinstance(vol, float):
            vol = float(vol)
        ratio = vol / avg
        if ratio > config.volume_mult:
            magnitude = f"volume {ratio:.1f}× 30d avg"
            severity: Literal["high", "medium"] = "high" if ratio >= 5.0 else "medium"
            events.append(
                AnomalyEvent(
                    date=str(idx)[:10],
                    kind="volume_surge",
                    magnitude=magnitude,
                    severity=severity,
                )
            )
    return events


def _detect_gap_events(
    open_: pd.Series[Any],
    close: pd.Series[Any],
    config: DetectorConfig,
) -> list[AnomalyEvent]:
    gap = open_ / close.shift(1) - 1

    events: list[AnomalyEvent] = []
    for idx in gap.index:
        g = gap.loc[idx]
        if not isinstance(g, float):
            g = float(g)
        if math.isnan(g):
            continue
        if abs(g) * 100 > config.gap_pct:
            magnitude = f"gap {g * 100:+.1f}%"
            severity: Literal["high", "medium"] = "high" if abs(g) * 100 >= 7.0 else "medium"
            events.append(
                AnomalyEvent(
                    date=str(idx)[:10],
                    kind="gap",
                    magnitude=magnitude,
                    severity=severity,
                )
            )
    return events


def _sort_and_truncate(events: list[AnomalyEvent], max_n: int) -> list[AnomalyEvent]:
    """Sort: high severity first, then by date descending within each severity level."""
    high = sorted(
        [e for e in events if e.severity == "high"],
        key=lambda e: e.date,
        reverse=True,
    )
    medium = sorted(
        [e for e in events if e.severity == "medium"],
        key=lambda e: e.date,
        reverse=True,
    )
    return (high + medium)[:max_n]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_anomalies(df: pd.DataFrame, config: DetectorConfig | None = None) -> AnomalyReport:
    """Detect price, volume, and gap anomalies in a validated OHLCV DataFrame."""
    _validate(df)

    if config is None:
        config = DetectorConfig()

    close = df["Close"].astype(float)
    volume = df["Volume"].astype(float)
    open_ = df["Open"].astype(float)

    raw: list[AnomalyEvent] = []
    raw.extend(_detect_price_events(close, config))
    raw.extend(_detect_volume_events(volume, config))
    raw.extend(_detect_gap_events(open_, close, config))

    # Deduplicate: one event per (date, kind)
    seen: set[tuple[str, str]] = set()
    deduped: list[AnomalyEvent] = []
    for e in raw:
        key = (e.date, e.kind)
        if key not in seen:
            seen.add(key)
            deduped.append(e)

    anomalies = _sort_and_truncate(deduped, MAX_ANOMALIES)
    return AnomalyReport(anomalies=anomalies, detector_config=config)


__all__ = ["AnomalyEvent", "AnomalyReport", "DetectorConfig", "detect_anomalies"]
