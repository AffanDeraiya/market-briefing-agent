"""Record frozen OHLCV fixtures for the eval suite (techspec §7).

Run manually when (re)freezing fixtures — never in CI:
    uv run python -m evals.record_fixtures

Refreezing invalidates evals/fixtures/labels.json: re-inspect and re-label.
"""

from pathlib import Path

import yfinance as yf

FIXTURE_TICKERS = ["AAPL", "TSLA", "NVDA", "MSFT", "RELIANCE.NS"]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def record() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for ticker in FIXTURE_TICKERS:
        df = yf.Ticker(ticker).history(period="1y", auto_adjust=True)
        if df.empty:
            raise RuntimeError(f"no data for {ticker}")
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = df.index.tz_localize(None).normalize()
        safe_name = ticker.replace(".", "_")
        path = FIXTURES_DIR / f"{safe_name}_1y.parquet"
        df.to_parquet(path)
        print(f"{ticker}: {len(df)} rows -> {path.name}")


if __name__ == "__main__":
    record()
