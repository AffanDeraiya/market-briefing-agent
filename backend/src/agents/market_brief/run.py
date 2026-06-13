"""Phase 1 demo CLI — prints each tool's output for a given ticker.

No LLM, no agent loop. Run with:
    uv run python -m src.agents.market_brief.run AAPL
    uv run python -m src.agents.market_brief.run AAPL --period 3mo
"""

from __future__ import annotations

import argparse

from src.agents.market_brief.state import PERIODS, Period
from src.agents.market_brief.utils import search
from src.agents.market_brief.utils.anomalies import detect_anomalies
from src.agents.market_brief.utils.indicators import compute_indicators
from src.agents.market_brief.utils.market_data import (
    fetch_ohlcv,
    get_fundamentals,
    get_price_history,
)

_SEP = "=" * 60


def _section(title: str) -> None:
    print(f"\n{_SEP}\n  {title}\n{_SEP}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Market Briefing Agent — Phase 1 tool demo (no LLM)."
    )
    parser.add_argument("ticker", type=str, help="Stock ticker symbol, e.g. AAPL")
    parser.add_argument(
        "--period",
        choices=list(PERIODS),
        default="1y",
        help="Historical period (default: 1y)",
    )
    args = parser.parse_args()

    ticker: str = args.ticker.upper()
    period: Period = args.period  # already validated by argparse choices

    print(f"\nMarket Briefing Agent — demo run for {ticker} / period={period}")

    # 1. Price history
    _section("get_price_history")
    price_history = get_price_history(ticker, period)
    print(price_history.model_dump_json(indent=2))

    # 2. Fundamentals
    _section("get_fundamentals")
    fundamentals = get_fundamentals(ticker)
    print(fundamentals.model_dump_json(indent=2))

    # 3. OHLCV → indicators + anomalies
    df = fetch_ohlcv(ticker, period)

    _section("compute_indicators")
    indicators = compute_indicators(df)
    print(indicators.model_dump_json(indent=2))

    _section("detect_anomalies")
    anomaly_report = detect_anomalies(df)
    print(anomaly_report.model_dump_json(indent=2))

    # 4. Company news (may fail offline; don't crash the demo)
    _section("get_company_news")
    try:
        news = search.get_company_news(f"{ticker} stock")
        print(news.model_dump_json(indent=2))
    except search.SearchError as exc:
        print(f"news search skipped: {exc}")


if __name__ == "__main__":
    main()
