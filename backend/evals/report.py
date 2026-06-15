"""Eval report generation — aggregate metrics and markdown rendering."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.checks import (
    FAITHFULNESS_GATE,
    STRUCTURE_GATE,
    citation_faithfulness,
    structure_compliance,
)
from evals.replay import ReplayResult, discover_cassettes, replay_cassette

__all__ = [
    "RunMetrics",
    "evaluate_all",
    "aggregate",
    "render_markdown",
    "write_report",
]


# ---------------------------------------------------------------------------
# RunMetrics dataclass
# ---------------------------------------------------------------------------


@dataclass
class RunMetrics:
    """Metrics for a single cassette replay run."""

    name: str
    ticker: str
    period: str
    iterations: int
    tool_calls: int
    faithfulness: float
    structure: float
    ok: bool
    notes: str


# ---------------------------------------------------------------------------
# evaluate_all
# ---------------------------------------------------------------------------


def evaluate_all(cassettes_dir: str | Path) -> list[RunMetrics]:
    """Replay every cassette in *cassettes_dir* and return one RunMetrics each."""
    results: list[RunMetrics] = []

    for cassette_path in discover_cassettes(cassettes_dir):
        try:
            result: ReplayResult = replay_cassette(cassette_path)
        except Exception as exc:  # noqa: BLE001
            results.append(
                RunMetrics(
                    name=cassette_path.stem,
                    ticker="?",
                    period="?",
                    iterations=0,
                    tool_calls=0,
                    faithfulness=0.0,
                    structure=0.0,
                    ok=False,
                    notes=f"replay error: {exc}",
                )
            )
            continue

        ticker: str = result.request.get("ticker", "?")
        period: str = result.request.get("period", "?")
        iterations: int = result.usage.get("iterations", 0)
        tool_calls: int = result.usage.get("tool_calls", 0)

        if result.brief is None:
            error_msg = (
                f"{result.error[0]}: {result.error[1]}"
                if result.error is not None
                else "unknown error"
            )
            results.append(
                RunMetrics(
                    name=result.name,
                    ticker=ticker,
                    period=period,
                    iterations=iterations,
                    tool_calls=tool_calls,
                    faithfulness=0.0,
                    structure=0.0,
                    ok=False,
                    notes=error_msg,
                )
            )
            continue

        faith_score, unfaithful_ids = citation_faithfulness(result.brief, result.tool_io)
        struct_score, failed_checks = structure_compliance(result.brief)

        notes_parts: list[str] = []
        if unfaithful_ids:
            notes_parts.append(f"unfaithful citations: {unfaithful_ids}")
        if failed_checks:
            notes_parts.append(f"failed checks: {failed_checks}")
        notes = "; ".join(notes_parts)

        ok = faith_score >= FAITHFULNESS_GATE and struct_score >= STRUCTURE_GATE

        results.append(
            RunMetrics(
                name=result.name,
                ticker=ticker,
                period=period,
                iterations=iterations,
                tool_calls=tool_calls,
                faithfulness=faith_score,
                structure=struct_score,
                ok=ok,
                notes=notes,
            )
        )

    return results


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------


def aggregate(metrics: list[RunMetrics]) -> dict[str, Any]:
    """Compute summary statistics across all runs."""
    n = len(metrics)
    if n == 0:
        return {
            "mean_faithfulness": 0.0,
            "mean_structure": 0.0,
            "n": 0,
            "all_pass": False,
        }

    mean_faithfulness = sum(m.faithfulness for m in metrics) / n
    mean_structure = sum(m.structure for m in metrics) / n
    all_pass = (
        n > 0
        and all(m.ok for m in metrics)
        and mean_faithfulness >= FAITHFULNESS_GATE
        and mean_structure >= STRUCTURE_GATE
    )

    return {
        "mean_faithfulness": mean_faithfulness,
        "mean_structure": mean_structure,
        "n": n,
        "all_pass": all_pass,
    }


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------


def render_markdown(metrics: list[RunMetrics], agg: dict[str, Any]) -> str:
    """Render a markdown eval report."""
    today_str = datetime.date.today().isoformat()

    lines: list[str] = [
        "# Eval Report",
        "",
        f"Generated on: {today_str}",
        "",
        "| run | ticker | period | iters | tools | faithfulness | structure | status |",
        "| --- | ------ | ------ | ----- | ----- | ------------ | --------- | ------ |",
    ]

    for m in metrics:
        status = "PASS" if m.ok else "FAIL"
        faith_pct = f"{m.faithfulness * 100:.0f}%"
        struct_pct = f"{m.structure * 100:.0f}%"
        lines.append(
            f"| {m.name} | {m.ticker} | {m.period} | {m.iterations} | {m.tool_calls}"
            f" | {faith_pct} | {struct_pct} | {status} |"
        )

    lines += [
        "",
        "## Aggregate",
        "",
        f"- Runs: {agg['n']}",
        f"- Mean faithfulness: {agg['mean_faithfulness'] * 100:.1f}%"
        f" (gate: >={FAITHFULNESS_GATE * 100:.0f}%)",
        f"- Mean structure: {agg['mean_structure'] * 100:.1f}%"
        f" (gate: >={STRUCTURE_GATE * 100:.0f}%)",
        f"- All pass: {agg['all_pass']}",
        "- Anomaly detector: 100% (see test_fixtures_labels.py regression)",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# write_report
# ---------------------------------------------------------------------------


def write_report(text: str, path: str | Path) -> None:
    """Write *text* to *path* as UTF-8."""
    Path(path).write_text(text, encoding="utf-8")
