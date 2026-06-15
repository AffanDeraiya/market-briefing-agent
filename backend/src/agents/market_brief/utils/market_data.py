"""yfinance adapter with 24h disk cache (techspec §1, §4).

Outputs are compact by design: the LLM gets summaries (weekly aggregates +
notable days), never raw OHLCV rows. Raw frames stay server-side for the
chart event and the indicator/anomaly functions.

The 10s tool timeout is enforced by the tool executor (Phase 2), not here —
yfinance does not expose a reliable per-request timeout.
"""

import contextlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
from pydantic import BaseModel

from ..state import CACHE_TTL_HOURS, Period

_BACKEND_ROOT = Path(__file__).resolve().parents[4]
OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


class TickerNotFoundError(ValueError):
    """Raised when yfinance returns no data for a ticker/period."""


class WeekAggregate(BaseModel):
    week_start: str
    close: float
    volume: int


class NotableDay(BaseModel):
    date: str
    close: float
    ret_pct: float
    volume: int


class ChangePct(BaseModel):
    d1: float | None
    m1: float | None
    period: float | None


class PriceHistory(BaseModel):
    currency: str | None
    latest_close: float
    change_pct: ChangePct
    week_aggregates: list[WeekAggregate]
    notable_days: list[NotableDay]
    high_52w: float | None
    low_52w: float | None


class Fundamentals(BaseModel):
    name: str | None
    exchange: str | None
    sector: str | None
    industry: str | None
    market_cap: int | None
    pe_trailing: float | None
    pe_forward: float | None
    dividend_yield: float | None
    next_earnings_date: str | None
    beta: float | None


def cache_dir() -> Path:
    path = Path(os.environ.get("MBA_CACHE_DIR", _BACKEND_ROOT / ".cache"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_fresh(path: Path) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < CACHE_TTL_HOURS * 3600


def _evict_cache_if_needed() -> None:
    """Best-effort LRU eviction: delete oldest files when the cache exceeds MAX_CACHE_FILES.

    Called after each cache-miss write in fetch_ohlcv / fetch_info.  Never
    raises — eviction failure is non-fatal and must not break the caller.
    """
    try:
        max_files = int(os.environ.get("MAX_CACHE_FILES", "200"))
        d = cache_dir()
        files = list(d.iterdir())
        if len(files) <= max_files:
            return
        # Sort oldest-first by modification time, delete until within cap.
        files.sort(key=lambda p: p.stat().st_mtime)
        for f in files[: len(files) - max_files]:
            with contextlib.suppress(OSError):
                f.unlink(missing_ok=True)  # best-effort
    except Exception:  # noqa: BLE001
        pass  # eviction is never allowed to raise


def fetch_ohlcv(ticker: str, period: Period) -> pd.DataFrame:
    """OHLCV frame for ticker/period, cached on disk for 24h."""
    cached = cache_dir() / f"{ticker.upper()}_{period}.parquet"
    if _is_fresh(cached):
        cached_df: pd.DataFrame = pd.read_parquet(cached)
        return cached_df

    df: pd.DataFrame = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    if df.empty:
        raise TickerNotFoundError(f"No price data for ticker {ticker!r} (period {period})")
    df = df[OHLCV_COLUMNS].copy()
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    df.to_parquet(cached)
    # Evict old cache entries AFTER writing so the new file is always kept.
    _evict_cache_if_needed()
    return df


def fetch_info(ticker: str) -> dict[str, Any]:
    """Raw yfinance info dict, cached on disk for 24h. Empty dict on upstream failure."""
    cached = cache_dir() / f"{ticker.upper()}_info.json"
    if _is_fresh(cached):
        loaded: dict[str, Any] = json.loads(cached.read_text(encoding="utf-8"))
        return loaded

    try:
        info: dict[str, Any] = dict(yf.Ticker(ticker).info or {})
    except Exception:
        info = {}
    if info:
        cached.write_text(json.dumps(info), encoding="utf-8")
        # Evict old cache entries AFTER writing so the new file is always kept.
        _evict_cache_if_needed()
    return info


def _pct(later: float, earlier: float) -> float | None:
    if earlier == 0 or math.isnan(earlier) or math.isnan(later):
        return None
    return round((later / earlier - 1) * 100, 2)


def get_price_history(ticker: str, period: Period) -> PriceHistory:
    df = fetch_ohlcv(ticker, period)
    close = df["Close"]
    latest = float(close.iloc[-1])

    weekly = df.resample("W-MON", label="left", closed="left").agg(
        {"Close": "last", "Volume": "sum"}
    )
    weekly = weekly.dropna(subset=["Close"])
    week_aggregates = [
        WeekAggregate(
            week_start=ts.date().isoformat(),
            close=round(float(c), 2),
            volume=int(v),
        )
        for ts, c, v in zip(
            pd.DatetimeIndex(weekly.index), weekly["Close"], weekly["Volume"], strict=True
        )
    ]

    rets = close.pct_change()
    notable_idx = rets.abs().nlargest(5).index
    notable_days = sorted(
        (
            NotableDay(
                date=idx.date().isoformat(),
                close=round(float(close.loc[idx]), 2),
                ret_pct=round(float(rets.loc[idx]) * 100, 2),
                volume=int(df["Volume"].loc[idx]),
            )
            for idx in notable_idx
            if not math.isnan(float(rets.loc[idx]))
        ),
        key=lambda d: d.date,
    )

    # 52-week range needs a year of data regardless of requested period (separate cache entry)
    try:
        year = df if period == "1y" else fetch_ohlcv(ticker, "1y")
        high_52w: float | None = round(float(year["Close"].max()), 2)
        low_52w: float | None = round(float(year["Close"].min()), 2)
    except (TickerNotFoundError, OSError):
        high_52w = low_52w = None

    month_ago = min(21, len(close) - 1)
    return PriceHistory(
        currency=fetch_info(ticker).get("currency"),
        latest_close=round(latest, 2),
        change_pct=ChangePct(
            d1=_pct(latest, float(close.iloc[-2])) if len(close) >= 2 else None,
            m1=_pct(latest, float(close.iloc[-1 - month_ago])) if month_ago > 0 else None,
            period=_pct(latest, float(close.iloc[0])) if len(close) >= 2 else None,
        ),
        week_aggregates=week_aggregates,
        notable_days=notable_days,
        high_52w=high_52w,
        low_52w=low_52w,
    )


def get_fundamentals(ticker: str) -> Fundamentals:
    """Fundamentals from yfinance info; nulls allowed, never invented (schema.md §2)."""
    info = fetch_info(ticker)
    if not info or info.get("shortName") is None and info.get("longName") is None:
        # Distinguish bad ticker from sparse info: price data existing means ticker is real
        fetch_ohlcv(ticker, "1mo")

    earnings_ts = info.get("earningsTimestampStart") or info.get("earningsTimestamp")
    next_earnings = (
        time.strftime("%Y-%m-%d", time.gmtime(earnings_ts))
        if isinstance(earnings_ts, int | float)
        else None
    )

    def _num(key: str) -> float | None:
        val = info.get(key)
        return float(val) if isinstance(val, int | float) and not isinstance(val, bool) else None

    market_cap = info.get("marketCap")
    return Fundamentals(
        name=info.get("shortName") or info.get("longName"),
        exchange=info.get("fullExchangeName") or info.get("exchange"),
        sector=info.get("sector"),
        industry=info.get("industry"),
        market_cap=int(market_cap) if isinstance(market_cap, int | float) else None,
        pe_trailing=_num("trailingPE"),
        pe_forward=_num("forwardPE"),
        dividend_yield=_num("dividendYield"),
        next_earnings_date=next_earnings,
        beta=_num("beta"),
    )
