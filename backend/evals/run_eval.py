"""Offline eval CLI — replays cassettes, checks gates, writes the markdown report.

Run from the backend directory:
    python -m evals.run_eval
    python -m evals.run_eval --cassettes-dir evals/cassettes --report evals/report.md

Returns exit code 0 when all gates pass, 1 otherwise.
CI runs this step after pytest; it never makes live API calls.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

__all__ = ["main"]

# Default paths relative to this file (backend/evals/run_eval.py)
_HERE = Path(__file__).parent
_DEFAULT_CASSETTES = _HERE / "cassettes"
_DEFAULT_REPORT = _HERE / "report.md"


def main() -> int:
    """Entry point for the eval CLI. Returns 0 on all-pass, 1 on any failure."""
    parser = argparse.ArgumentParser(
        description="Offline eval — replay cassettes and check metric gates.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--cassettes-dir",
        default=str(_DEFAULT_CASSETTES),
        help="Directory containing *.json cassette files",
    )
    parser.add_argument(
        "--report",
        default=str(_DEFAULT_REPORT),
        help="Path to write the markdown eval report",
    )
    args = parser.parse_args()

    from evals.checks import FAITHFULNESS_GATE, STRUCTURE_GATE
    from evals.replay import discover_cassettes
    from evals.report import aggregate, evaluate_all, render_markdown, write_report

    cassettes_dir = Path(args.cassettes_dir)
    found = discover_cassettes(cassettes_dir)
    if not found:
        print(
            f"No cassettes found in {cassettes_dir}. "
            "Run `make eval-live` to record cassettes first.",
            file=sys.stderr,
        )
        return 1

    print(f"Replaying {len(found)} cassette(s) from {cassettes_dir} …")
    metrics = evaluate_all(cassettes_dir)
    agg = aggregate(metrics)

    # ── Summary table to stdout ───────────────────────────────────────────
    header = f"{'run':<30} {'ticker':<12} {'period':<8} {'faith':>8} {'struct':>8} {'status'}"
    print()
    print(header)
    print("-" * len(header))
    for m in metrics:
        status = "PASS" if m.ok else "FAIL"
        print(
            f"{m.name:<30} {m.ticker:<12} {m.period:<8}"
            f" {m.faithfulness * 100:>7.0f}%"
            f" {m.structure * 100:>7.0f}%"
            f"  {status}"
        )
        if m.notes:
            print(f"  notes: {m.notes}")
    print()

    # ── Gate summary ─────────────────────────────────────────────────────
    faith_pct = agg["mean_faithfulness"] * 100
    struct_pct = agg["mean_structure"] * 100
    gate_faith = FAITHFULNESS_GATE * 100
    gate_struct = STRUCTURE_GATE * 100

    print(f"Faithfulness: {faith_pct:.1f}% (gate: >={gate_faith:.0f}%)")
    print(f"Structure:    {struct_pct:.1f}% (gate: >={gate_struct:.0f}%)")
    print()

    if agg["all_pass"]:
        print("PASS — all eval gates met.")
    else:
        print("FAIL — one or more eval gates not met.", file=sys.stderr)

    # ── Markdown report ───────────────────────────────────────────────────
    report_path = Path(args.report)
    report_text = render_markdown(metrics, agg)
    write_report(report_text, report_path)
    print(f"\nReport written to: {report_path}")

    return 0 if agg["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
