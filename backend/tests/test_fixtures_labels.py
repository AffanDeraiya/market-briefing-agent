"""Detector regression test — frozen parquet fixtures vs. hand-labeled ground truth.

Loads each fixture from evals/fixtures/, runs detect_anomalies, and asserts
the (date, kind, severity) tuples exactly match labels.json in order.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.agents.market_brief.utils.anomalies import detect_anomalies

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "evals" / "fixtures"
_LABELS_FILE = _FIXTURES_DIR / "labels.json"


def _load_labels() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_LABELS_FILE.read_text(encoding="utf-8"))
    return data


_LABELS: dict[str, Any] = _load_labels()

# Fixture stems to parametrize — skip metadata keys that start with "_"
_STEMS: list[str] = [k for k in _LABELS if not k.startswith("_")]


# ---------------------------------------------------------------------------
# Existence guard
# ---------------------------------------------------------------------------


def test_all_fixture_parquets_exist() -> None:
    """Every stem in labels.json must have a corresponding parquet on disk."""
    missing: list[str] = []
    for stem in _STEMS:
        path = _FIXTURES_DIR / f"{stem}.parquet"
        if not path.exists():
            missing.append(str(path))
    assert not missing, "Missing fixture parquets:\n" + "\n".join(missing)


# ---------------------------------------------------------------------------
# Per-ticker regression tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stem", _STEMS)
def test_detector_matches_labels(stem: str) -> None:
    """detect_anomalies on frozen parquet must exactly reproduce labeled (date, kind, severity)."""
    parquet_path = _FIXTURES_DIR / f"{stem}.parquet"
    df: pd.DataFrame = pd.read_parquet(parquet_path)
    report = detect_anomalies(df)

    expected: list[tuple[str, str, str]] = [
        (a["date"], a["kind"], a["severity"]) for a in _LABELS[stem]["anomalies"]
    ]
    actual: list[tuple[str, str, str]] = [(e.date, e.kind, e.severity) for e in report.anomalies]

    assert actual == expected, (
        f"[{stem}] detector output does not match labels.\n"
        f"  expected ({len(expected)}): {expected}\n"
        f"  actual   ({len(actual)}):   {actual}"
    )
