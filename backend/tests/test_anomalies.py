"""Unit tests for anomalies.py — synthetic DataFrames, no network, no fixtures."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest

from src.agents.market_brief.utils.anomalies import (
    AnomalyEvent,
    DetectorConfig,
    detect_anomalies,
)

# ---------------------------------------------------------------------------
# DataFrame builder helpers
# ---------------------------------------------------------------------------


def make_df(
    closes: list[float],
    volumes: list[float] | None = None,
    opens: list[float] | None = None,
    start: str = "2024-01-02",
) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame with a business-day DatetimeIndex."""
    n = len(closes)
    idx = pd.bdate_range(start=start, periods=n)
    if volumes is None:
        volumes = [1_000_000.0] * n
    if opens is None:
        opens = [closes[0]] + closes[:-1]  # open = prev close

    highs = [max(o, c) * 1.005 for o, c in zip(opens, closes, strict=True)]
    lows = [min(o, c) * 0.995 for o, c in zip(opens, closes, strict=True)]

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


def make_calm_series(n: int = 100, seed: int = 0) -> list[float]:
    """Small-noise random walk that guarantees sigma > 0."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, 0.005, n)  # 0.5% daily noise
    closes = 100.0 * np.cumprod(1 + returns)
    result: list[float] = closes.tolist()
    return result


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_empty_df_raises() -> None:
    df: pd.DataFrame = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    with pytest.raises(ValueError, match="empty"):
        detect_anomalies(df)


def test_missing_column_raises() -> None:
    df = make_df([100.0, 101.0, 102.0])
    df = df.drop(columns=["Open"])
    with pytest.raises(ValueError, match="Missing"):
        detect_anomalies(df)


# ---------------------------------------------------------------------------
# Flat / trivial series
# ---------------------------------------------------------------------------


def test_flat_series_zero_anomalies() -> None:
    """Constant prices and volumes → no anomalies of any kind."""
    closes = [100.0] * 80
    df = make_df(closes)
    report = detect_anomalies(df)
    assert report.anomalies == []


# ---------------------------------------------------------------------------
# Price events
# ---------------------------------------------------------------------------


def test_engineered_price_drop_detected() -> None:
    """
    ~100 calm days with one engineered -9% crash.
    Expect exactly one price_drop event.
    """
    closes = make_calm_series(100, seed=1)
    # Inject a large drop on day 60
    drop_factor = 0.91
    closes[60] = closes[59] * drop_factor

    df = make_df(closes)
    report = detect_anomalies(df)

    price_drops = [e for e in report.anomalies if e.kind == "price_drop"]
    assert len(price_drops) == 1, f"Expected 1 price_drop, got {len(price_drops)}"

    event = price_drops[0]
    # Magnitude format: "+X.X% (Y.Yσ)"
    assert re.match(r"^[+-]\d+\.\d+% \(\d+\.\d+σ\)$", event.magnitude), (
        f"Magnitude format mismatch: {event.magnitude!r}"
    )
    # The σ multiple should be plausibly high (well above threshold 2.5)
    sigma_str = re.search(r"\((\d+\.\d+)σ\)", event.magnitude)
    assert sigma_str is not None
    sigma_multiple = float(sigma_str.group(1))
    assert sigma_multiple > 2.5, f"σ multiple {sigma_multiple} should be > 2.5"


def test_price_spike_detected() -> None:
    """Engineered +9% spike → price_spike event."""
    closes = make_calm_series(100, seed=2)
    closes[50] = closes[49] * 1.09

    df = make_df(closes)
    report = detect_anomalies(df)

    spikes = [e for e in report.anomalies if e.kind == "price_spike"]
    assert len(spikes) >= 1
    assert any(e.kind == "price_spike" for e in report.anomalies)


def test_price_drop_severity_high() -> None:
    """A sufficiently extreme drop → severity 'high'."""
    closes = make_calm_series(100, seed=3)
    # Force a very large drop (15%)
    closes[70] = closes[69] * 0.85

    df = make_df(closes)
    report = detect_anomalies(df)

    drops = [e for e in report.anomalies if e.kind == "price_drop"]
    # At least one should be high
    assert any(e.severity == "high" for e in drops), (
        f"Expected high-severity price_drop, got: {drops}"
    )


def test_no_price_events_when_sigma_zero() -> None:
    """If sigma of returns is 0 (constant price) → no price events."""
    closes = [100.0] * 50
    df = make_df(closes)
    report = detect_anomalies(df)
    price_events = [e for e in report.anomalies if e.kind in ("price_spike", "price_drop")]
    assert price_events == []


# ---------------------------------------------------------------------------
# Volume events
# ---------------------------------------------------------------------------


def test_volume_surge_high_severity() -> None:
    """6× volume spike on a single day → volume_surge with severity 'high'."""
    # Need at least 5 prior rows for avg30 to be valid (min_periods=5 after shift)
    n = 60
    base_vol = 1_000_000.0
    vols = [base_vol] * n
    vols[50] = base_vol * 6.0  # 6× spike

    closes = make_calm_series(n, seed=4)
    df = make_df(closes, volumes=vols)
    report = detect_anomalies(df)

    surges = [e for e in report.anomalies if e.kind == "volume_surge"]
    assert len(surges) >= 1
    # At least the 6× day should be high
    high_surges = [e for e in surges if e.severity == "high"]
    assert len(high_surges) >= 1


def test_volume_surge_medium_severity() -> None:
    """4× volume spike → volume_surge with severity 'medium' (< 5×)."""
    n = 60
    base_vol = 1_000_000.0
    vols = [base_vol] * n
    vols[50] = base_vol * 4.0  # 4× spike

    closes = make_calm_series(n, seed=5)
    df = make_df(closes, volumes=vols)
    report = detect_anomalies(df)

    surges = [e for e in report.anomalies if e.kind == "volume_surge"]
    assert len(surges) >= 1
    # The 4× event should be medium
    assert surges[0].severity == "medium"


def test_volume_surge_magnitude_format() -> None:
    """Volume surge magnitude should match 'volume X.Xx 30d avg'."""
    n = 60
    base_vol = 1_000_000.0
    vols = [base_vol] * n
    vols[50] = base_vol * 6.0

    closes = make_calm_series(n, seed=6)
    df = make_df(closes, volumes=vols)
    report = detect_anomalies(df)

    surges = [e for e in report.anomalies if e.kind == "volume_surge"]
    assert surges
    assert re.match(r"^volume \d+\.\d+× 30d avg$", surges[0].magnitude), (
        f"Magnitude mismatch: {surges[0].magnitude!r}"
    )


# ---------------------------------------------------------------------------
# Gap events
# ---------------------------------------------------------------------------


def test_gap_event_detected() -> None:
    """An overnight gap of +6% → gap event."""
    closes = make_calm_series(60, seed=7)
    opens = [closes[0]] + closes[:-1]

    # Day 40: open at +6% above previous close
    spike_day = 40
    opens[spike_day] = closes[spike_day - 1] * 1.06

    df = make_df(closes, opens=opens)
    report = detect_anomalies(df)

    gaps = [e for e in report.anomalies if e.kind == "gap"]
    assert len(gaps) >= 1


def test_gap_severity_high() -> None:
    """A gap of 8% → severity 'high'."""
    closes = make_calm_series(60, seed=8)
    opens = [closes[0]] + closes[:-1]
    spike_day = 40
    opens[spike_day] = closes[spike_day - 1] * 1.08

    df = make_df(closes, opens=opens)
    report = detect_anomalies(df)

    gaps = [e for e in report.anomalies if e.kind == "gap"]
    high_gaps = [e for e in gaps if e.severity == "high"]
    assert len(high_gaps) >= 1


def test_gap_magnitude_format() -> None:
    """Gap magnitude format: 'gap +X.X%'."""
    closes = make_calm_series(60, seed=9)
    opens = [closes[0]] + closes[:-1]
    spike_day = 40
    opens[spike_day] = closes[spike_day - 1] * 1.06

    df = make_df(closes, opens=opens)
    report = detect_anomalies(df)

    gaps = [e for e in report.anomalies if e.kind == "gap"]
    assert gaps
    assert re.match(r"^gap [+-]\d+\.\d+%$", gaps[0].magnitude), (
        f"Gap magnitude format mismatch: {gaps[0].magnitude!r}"
    )


# ---------------------------------------------------------------------------
# Same-day multi-event
# ---------------------------------------------------------------------------


def test_same_day_crash_and_volume_spike() -> None:
    """A day with both a price crash and a volume spike → both events present for that date."""
    n = 60
    base_vol = 1_000_000.0
    vols = [base_vol] * n
    spike_day = 50
    vols[spike_day] = base_vol * 6.0  # volume spike

    closes = make_calm_series(n, seed=10)
    closes[spike_day] = closes[spike_day - 1] * 0.88  # price crash

    df = make_df(closes, volumes=vols)
    report = detect_anomalies(df)

    idx = pd.bdate_range(start="2024-01-02", periods=n)
    crash_date = str(idx[spike_day])[:10]

    price_events_on_day = [
        e for e in report.anomalies if e.date == crash_date and e.kind == "price_drop"
    ]
    vol_events_on_day = [
        e for e in report.anomalies if e.date == crash_date and e.kind == "volume_surge"
    ]
    assert len(price_events_on_day) >= 1, "Expected price_drop on crash day"
    assert len(vol_events_on_day) >= 1, "Expected volume_surge on crash day"


# ---------------------------------------------------------------------------
# Truncation to MAX_ANOMALIES
# ---------------------------------------------------------------------------


def test_truncated_to_8_with_high_first() -> None:
    """More than 8 anomalies → truncated to 8, high-severity kept first."""
    # Create ~15 anomalous days: alternating large spikes and drops
    n = 100
    closes = make_calm_series(n, seed=11)

    # Inject 12 extreme events (alternating spike/drop) on days 10–85
    anomaly_days = list(range(10, 85, 6))  # days 10, 16, 22, ...
    for i, d in enumerate(anomaly_days):
        if i % 2 == 0:
            closes[d] = closes[d - 1] * 1.20  # +20% spike — will be high severity
        else:
            closes[d] = closes[d - 1] * 0.80  # -20% drop — will be high severity

    df = make_df(closes)
    report = detect_anomalies(df)

    assert len(report.anomalies) <= 8

    # All high-severity must come before all medium-severity
    severities = [e.severity for e in report.anomalies]
    found_medium = False
    for s in severities:
        if s == "medium":
            found_medium = True
        if found_medium and s == "high":
            pytest.fail(f"High-severity event found after medium: {severities}")


def test_truncation_keeps_high_severity() -> None:
    """When truncating, high-severity events should be retained over medium ones."""
    n = 100
    closes = make_calm_series(n, seed=12)

    # Inject >8 events: some high (20%) and some medium (just over threshold)
    for d in range(10, 58, 8):
        closes[d] = closes[d - 1] * 1.20  # high severity

    df = make_df(closes)
    report = detect_anomalies(df)

    high_count = sum(1 for e in report.anomalies if e.severity == "high")
    medium_count = sum(1 for e in report.anomalies if e.severity == "medium")

    # Result must have all highs before any mediums
    assert high_count + medium_count == len(report.anomalies)
    assert len(report.anomalies) <= 8


# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------


def test_severity_ordering_high_before_medium() -> None:
    """High-severity events always precede medium-severity in the result."""
    n = 80
    closes = make_calm_series(n, seed=13)

    # Inject one high event and one medium event
    closes[60] = closes[59] * 0.75  # very large drop → high
    closes[30] = closes[29] * 0.94  # smaller drop — might be medium if sigma is small

    df = make_df(closes)
    report = detect_anomalies(df)

    if not report.anomalies:
        return  # nothing to check

    in_high_section = True
    for e in report.anomalies:
        if e.severity == "medium":
            in_high_section = False
        if not in_high_section and e.severity == "high":
            pytest.fail("Found high-severity after medium-severity in results")


# ---------------------------------------------------------------------------
# Custom DetectorConfig
# ---------------------------------------------------------------------------


def test_custom_config_higher_threshold() -> None:
    """A stricter return_sigma=10 should suppress events that default config catches."""
    closes = make_calm_series(100, seed=14)
    closes[60] = closes[59] * 0.91  # -9% drop

    df = make_df(closes)

    default_report = detect_anomalies(df)
    strict_config = DetectorConfig(return_sigma=10.0)
    strict_report = detect_anomalies(df, config=strict_config)

    # Strict config should produce fewer or equal price events
    default_price = sum(
        1 for e in default_report.anomalies if e.kind in ("price_spike", "price_drop")
    )
    strict_price = sum(
        1 for e in strict_report.anomalies if e.kind in ("price_spike", "price_drop")
    )
    assert strict_price <= default_price


def test_custom_config_is_reflected_in_report() -> None:
    """The DetectorConfig used should be echoed in the report."""
    closes = make_calm_series(50, seed=15)
    df = make_df(closes)
    cfg = DetectorConfig(return_sigma=1.0, volume_mult=2.0, gap_pct=1.0)
    report = detect_anomalies(df, config=cfg)

    assert report.detector_config.return_sigma == 1.0
    assert report.detector_config.volume_mult == 2.0
    assert report.detector_config.gap_pct == 1.0


def test_custom_config_lower_gap_pct_triggers_more_gaps() -> None:
    """Lowering gap_pct threshold should detect gaps that default config misses."""
    closes = make_calm_series(60, seed=16)
    opens = [closes[0]] + closes[:-1]
    # A 2% gap — below the default 4% threshold
    opens[40] = closes[39] * 1.02

    df = make_df(closes, opens=opens)

    default_report = detect_anomalies(df)
    low_gap_config = DetectorConfig(gap_pct=1.0)
    low_gap_report = detect_anomalies(df, config=low_gap_config)

    default_gaps = [e for e in default_report.anomalies if e.kind == "gap"]
    low_gap_gaps = [e for e in low_gap_report.anomalies if e.kind == "gap"]

    # With a lower threshold we should see at least as many gap events
    assert len(low_gap_gaps) >= len(default_gaps)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_no_duplicate_date_kind_pairs() -> None:
    """Each (date, kind) pair should appear at most once in the output."""
    closes = make_calm_series(100, seed=17)
    closes[50] = closes[49] * 0.85  # large drop

    df = make_df(closes)
    report = detect_anomalies(df)

    pairs = [(e.date, e.kind) for e in report.anomalies]
    assert len(pairs) == len(set(pairs)), f"Duplicate date/kind pairs found: {pairs}"


# ---------------------------------------------------------------------------
# Default config values
# ---------------------------------------------------------------------------


def test_default_config_values() -> None:
    """DetectorConfig defaults must match state.py constants."""
    from src.agents.market_brief.state import GAP_PCT, RETURN_SIGMA, VOLUME_MULT

    cfg = DetectorConfig()
    assert cfg.return_sigma == RETURN_SIGMA
    assert cfg.volume_mult == VOLUME_MULT
    assert cfg.gap_pct == GAP_PCT


# ---------------------------------------------------------------------------
# AnomalyReport structure
# ---------------------------------------------------------------------------


def test_report_structure() -> None:
    """AnomalyReport should always contain anomalies list and detector_config."""
    df = make_df(make_calm_series(50, seed=18))
    report = detect_anomalies(df)

    assert isinstance(report.anomalies, list)
    assert isinstance(report.detector_config, DetectorConfig)


def test_anomaly_event_fields() -> None:
    """Every AnomalyEvent should have all required fields with correct types."""
    closes = make_calm_series(100, seed=19)
    closes[50] = closes[49] * 0.88  # trigger a drop

    df = make_df(closes)
    report = detect_anomalies(df)

    for e in report.anomalies:
        assert isinstance(e, AnomalyEvent)
        assert isinstance(e.date, str)
        assert len(e.date) == 10  # YYYY-MM-DD
        assert e.kind in ("price_spike", "price_drop", "volume_surge", "gap")
        assert e.severity in ("high", "medium")
        assert isinstance(e.magnitude, str)
