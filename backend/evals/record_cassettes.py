"""Re-record eval cassettes from LIVE agent runs.

Requires GEMINI_API_KEY (loads backend/.env via python-dotenv).
Never run in CI.

Usage (from the backend directory):
    python -m evals.record_cassettes
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["EVAL_RUNS", "record_one", "main"]

# ---------------------------------------------------------------------------
# Cassette manifest — (ticker, period) pairs to record
# ---------------------------------------------------------------------------

EVAL_RUNS: list[tuple[str, str]] = [
    ("AAPL", "3mo"),
    ("MSFT", "6mo"),
    ("NVDA", "3mo"),
    ("TSLA", "6mo"),
    ("RELIANCE.NS", "1y"),
    ("AAPL", "1y"),
]

# Output directory: backend/evals/cassettes/
_CASSETTES_DIR = Path(__file__).parent / "cassettes"


def _cassette_filename(ticker: str, period: str) -> str:
    """Return the cassette filename for a given ticker and period.

    Dots in the ticker are replaced with underscores; the ticker is lower-cased.
    Examples:
        ("AAPL", "3mo")        → "aapl_3mo.json"
        ("RELIANCE.NS", "1y")  → "reliance_ns_1y.json"
    """
    safe_ticker = ticker.lower().replace(".", "_")
    return f"{safe_ticker}_{period}.json"


def record_one(ticker: str, period: str, out_dir: Path) -> None:
    """Record a single live agent run and dump the cassette to *out_dir*."""
    from dotenv import load_dotenv

    load_dotenv()

    from src.agents.market_brief.agent import run_agent
    from src.agents.market_brief.cassette import CassetteRecorder
    from src.agents.market_brief.events import make_stdout_emitter
    from src.llm import get_backend

    backend = get_backend()
    recorder = CassetteRecorder({"ticker": ticker, "period": period})

    result = run_agent(
        ticker,
        period,
        backend=backend,
        emit=make_stdout_emitter(),
        recorder=recorder,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    cassette_path = out_dir / _cassette_filename(ticker, period)
    recorder.dump(cassette_path)

    status = "ok" if result.brief is not None else f"error: {result.error}"
    print(f"  → {cassette_path} ({status})")


def main() -> int:
    """Record all EVAL_RUNS cassettes sequentially."""
    print(f"Recording {len(EVAL_RUNS)} cassette(s) into {_CASSETTES_DIR} …")
    for ticker, period in EVAL_RUNS:
        print(f"\n[{ticker} / {period}]")
        try:
            record_one(ticker, period, _CASSETTES_DIR)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {exc}", file=sys.stderr)
            return 1
    print("\nAll cassettes recorded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
