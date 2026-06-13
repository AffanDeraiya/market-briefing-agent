"""Market Briefing Agent — standalone CLI.

Two modes:

  Default (agent loop):
      uv run python -m src.agents.market_brief.run AAPL
      uv run python -m src.agents.market_brief.run AAPL --period 3mo
      uv run python -m src.agents.market_brief.run AAPL --record cassettes/aapl.json

  Phase-1 tools demo (no LLM, preserves backward compatibility):
      uv run python -m src.agents.market_brief.run AAPL --tools-only
"""

from __future__ import annotations

import argparse
import sys

from src.agents.market_brief.state import PERIODS, Period

_SEP = "=" * 60


# ---------------------------------------------------------------------------
# Phase-1 tools demo (legacy behaviour, kept for --tools-only)
# ---------------------------------------------------------------------------


def _section(title: str) -> None:
    print(f"\n{_SEP}\n  {title}\n{_SEP}")


def _run_tools_demo(ticker: str, period: Period) -> None:
    """Print each tool's raw output for *ticker* — no LLM required."""
    from src.agents.market_brief.utils import search
    from src.agents.market_brief.utils.anomalies import detect_anomalies
    from src.agents.market_brief.utils.indicators import compute_indicators
    from src.agents.market_brief.utils.market_data import (
        fetch_ohlcv,
        get_fundamentals,
        get_price_history,
    )

    print(f"\nMarket Briefing Agent — demo run for {ticker} / period={period}")

    _section("get_price_history")
    price_history = get_price_history(ticker, period)
    print(price_history.model_dump_json(indent=2))

    _section("get_fundamentals")
    fundamentals = get_fundamentals(ticker)
    print(fundamentals.model_dump_json(indent=2))

    df = fetch_ohlcv(ticker, period)

    _section("compute_indicators")
    indicators = compute_indicators(df)
    print(indicators.model_dump_json(indent=2))

    _section("detect_anomalies")
    anomaly_report = detect_anomalies(df)
    print(anomaly_report.model_dump_json(indent=2))

    _section("get_company_news")
    try:
        news = search.get_company_news(f"{ticker} stock")
        print(news.model_dump_json(indent=2))
    except search.SearchError as exc:
        print(f"news search skipped: {exc}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Market Briefing Agent — run the agent loop or the Phase-1 tool demo.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("ticker", type=str, help="Stock ticker symbol, e.g. AAPL")
    parser.add_argument(
        "--period",
        choices=list(PERIODS),
        default="1y",
        help="Historical period",
    )
    parser.add_argument(
        "--record",
        metavar="PATH",
        default=None,
        help="Save a replay cassette to PATH (JSON)",
    )
    parser.add_argument(
        "--tools-only",
        action="store_true",
        help="Phase-1 demo: print raw tool output, no LLM",
    )
    args = parser.parse_args()

    ticker: str = args.ticker.upper()
    period: Period = args.period  # already validated by argparse choices

    if args.tools_only:
        _run_tools_demo(ticker, period)
        return

    # ── Agent loop mode ───────────────────────────────────────────────────
    # Load backend/.env (gitignored) so GEMINI_API_KEY etc. are available.
    from dotenv import load_dotenv

    load_dotenv()

    try:
        from src.llm import get_backend

        backend = get_backend()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    from src.agents.market_brief.agent import run_agent
    from src.agents.market_brief.cassette import CassetteRecorder
    from src.agents.market_brief.events import make_stdout_emitter

    recorder: CassetteRecorder | None = None
    if args.record:
        recorder = CassetteRecorder({"ticker": ticker, "period": period})

    result = run_agent(
        ticker,
        period,
        backend=backend,
        emit=make_stdout_emitter(),
        recorder=recorder,
    )

    if recorder is not None and args.record:
        recorder.dump(args.record)
        print(f"\nCassette saved to: {args.record}")

    if result.brief is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
