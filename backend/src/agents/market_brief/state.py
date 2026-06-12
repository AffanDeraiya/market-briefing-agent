"""Agent state schema and contract constants (rules.md §A: first file a reader opens).

Run-state (history Turns, budgets) lands here in Phase 2; Phase 1 defines the
shared contract types the tool layer is built on.
"""

from typing import Literal

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
