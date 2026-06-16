"""Agent state schema and contract constants (rules.md §A: first file a reader opens).

Run-state (history Turns, budgets) lives in RunState below; the top section
defines the shared contract types the tool layer is built on.
"""

from __future__ import annotations

import os
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.llm import Turn

Period = Literal["1mo", "3mo", "6mo", "1y"]

PERIODS: tuple[Period, ...] = ("1mo", "3mo", "6mo", "1y")

# Detector thresholds (schema.md §2 detect_anomalies.detector_config)
RETURN_SIGMA = 2.5
VOLUME_MULT = 3.0
GAP_PCT = 4.0
MAX_ANOMALIES = 8

# Tool layer limits (techspec §4/§6)
TOOL_TIMEOUT_S = 10
SEARCH_MAX_RESULTS = 5
FETCH_PAGE_MAX_TOKENS = 2000
CACHE_TTL_HOURS = 24


# ---------------------------------------------------------------------------
# Budget helpers
# ---------------------------------------------------------------------------


def _env_int(name: str, default: int) -> int:
    """Read an integer from the environment; fall back to *default* if unset or non-integer."""
    raw = os.environ.get(name, "")
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


MAX_TOOL_CALLS: int = _env_int("MAX_TOOL_CALLS", 15)
MAX_ITERATIONS: int = _env_int("MAX_ITERATIONS", 20)
MAX_OUTPUT_TOKENS: int = _env_int("MAX_OUTPUT_TOKENS", 4096)
RUN_TIMEOUT_S: int = _env_int("RUN_TIMEOUT_S", 120)


# ---------------------------------------------------------------------------
# Mutable loop state
# ---------------------------------------------------------------------------


class RunState(BaseModel):
    """Mutable state threaded through the agent loop for one briefing run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ticker: str
    period: Period
    history: list[Turn] = Field(default_factory=list)
    iterations: int = 0
    tool_calls_made: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    started_at: float = Field(default_factory=time.monotonic)
    finalize_injected: bool = False
    repair_attempted: bool = False
    # date (ISO YYYY-MM-DD) -> kind; populated after detect_anomalies is called
    anomaly_dates: dict[str, str] = Field(default_factory=dict)
    # every URL seen in any tool result; used to reject ungrounded (fabricated)
    # news/web citations before the brief is finalized (rules.md: every claim cited)
    seen_urls: set[str] = Field(default_factory=set)
    # latest structured outputs captured for deterministic brief enrichment
    price_history_out: dict[str, Any] | None = None
    indicators_out: dict[str, Any] | None = None
    fundamentals_out: dict[str, Any] = Field(default_factory=dict)
    # full anomaly dicts from detect_anomalies (date, kind, magnitude, severity)
    anomalies_detail: list[dict[str, Any]] = Field(default_factory=list)

    def elapsed_s(self) -> float:
        """Seconds elapsed since this RunState was created."""
        return time.monotonic() - self.started_at

    def tool_budget_exceeded(self) -> bool:
        """True when the tool-call budget has been exhausted."""
        return self.tool_calls_made >= MAX_TOOL_CALLS

    def iteration_budget_exceeded(self) -> bool:
        """True when the iteration budget has been exhausted."""
        return self.iterations >= MAX_ITERATIONS

    def timed_out(self) -> bool:
        """True when the wall-clock run timeout has elapsed."""
        return self.elapsed_s() >= RUN_TIMEOUT_S

    def budget_reason(self) -> str | None:
        """Human-readable reason the run must stop, or None if still within budget."""
        if self.tool_budget_exceeded():
            return "tool budget"
        if self.iteration_budget_exceeded():
            return "iteration budget"
        if self.timed_out():
            return "run timeout"
        return None
