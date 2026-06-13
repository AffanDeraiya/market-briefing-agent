"""Input validation and rate-limit guards (techspec §6)."""

from __future__ import annotations

import os
import re
import threading
from datetime import UTC, datetime

__all__ = [
    "TICKER_RE",
    "normalize_ticker",
    "rate_limit_per_hour",
    "global_daily_cap",
    "DailyCounter",
    "daily_counter",
]

TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,12}$")


def normalize_ticker(raw: str) -> str:
    """Uppercase + strip; raise ValueError if the result doesn't match TICKER_RE."""
    candidate = raw.strip().upper()
    if not TICKER_RE.match(candidate):
        raise ValueError(f"Invalid ticker {raw!r}: must be 1–12 chars, A–Z 0–9 . -")
    return candidate


def rate_limit_per_hour() -> int:
    """Per-IP hourly brief limit, read from RATE_LIMIT_BRIEFS_PER_HOUR env var."""
    return int(os.environ.get("RATE_LIMIT_BRIEFS_PER_HOUR", "5"))


def global_daily_cap() -> int:
    """Global daily brief cap, read from GLOBAL_DAILY_BRIEFS env var."""
    return int(os.environ.get("GLOBAL_DAILY_BRIEFS", "100"))


class DailyCounter:
    """Thread-safe in-memory global daily brief counter (resets at UTC date change)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._date = datetime.now(UTC).date()
        self._count = 0

    def _refresh(self) -> None:
        """Caller must hold self._lock. Reset count if the UTC date has changed."""
        today = datetime.now(UTC).date()
        if today != self._date:
            self._date = today
            self._count = 0

    def remaining(self) -> int:
        """Remaining briefs today; clamped to >= 0. Reads global_daily_cap() live."""
        with self._lock:
            self._refresh()
            return max(0, global_daily_cap() - self._count)

    def try_consume(self) -> bool:
        """Consume one brief slot. Returns True on success, False if cap reached."""
        with self._lock:
            self._refresh()
            if self._count < global_daily_cap():
                self._count += 1
                return True
            return False

    def reset(self) -> None:
        """Reset counter — for tests."""
        with self._lock:
            self._date = datetime.now(UTC).date()
            self._count = 0


# Module-level singleton
daily_counter = DailyCounter()
