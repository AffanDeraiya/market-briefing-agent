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
    "rate_limit_per_day",
    "validate_rate_limit",
    "global_daily_cap",
    "DailyCounter",
    "daily_counter",
    "InFlightTracker",
    "inflight",
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


def rate_limit_per_day() -> int:
    """Per-IP daily brief limit, read from RATE_LIMIT_BRIEFS_PER_DAY env var."""
    return int(os.environ.get("RATE_LIMIT_BRIEFS_PER_DAY", "20"))


def validate_rate_limit() -> str:
    """Slowapi limit string for /api/validate, read from env per-request so tests can override."""
    return f"{int(os.environ.get('RATE_LIMIT_VALIDATE_PER_HOUR', '30'))}/hour"


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

    def refund(self) -> None:
        """Refund one brief slot — called when a run ends without producing a brief.

        Prevents garbage tickers or upstream errors from permanently draining the
        global daily budget.
        """
        with self._lock:
            self._refresh()
            if self._count > 0:
                self._count -= 1

    def reset(self) -> None:
        """Reset counter — for tests."""
        with self._lock:
            self._date = datetime.now(UTC).date()
            self._count = 0


# Module-level singleton
daily_counter = DailyCounter()


class InFlightTracker:
    """Thread-safe tracker for in-flight (concurrent) brief runs.

    Enforces both a global concurrency cap (MAX_CONCURRENT_GLOBAL) and a
    per-IP cap (MAX_CONCURRENT_PER_IP), read from env each call so that tests
    can override them without restarting the process.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._global = 0
        self._per_ip: dict[str, int] = {}

    def try_acquire(self, ip: str) -> bool:
        """Attempt to register a new in-flight run for *ip*.

        Caps are read from environment variables on each call so that tests
        can set them via monkeypatch/setenv without reinstantiating the object.

        Returns True if the slot was acquired, False if either cap is reached.
        """
        max_global = int(os.environ.get("MAX_CONCURRENT_GLOBAL", "6"))
        max_per_ip = int(os.environ.get("MAX_CONCURRENT_PER_IP", "2"))
        with self._lock:
            if self._global >= max_global or self._per_ip.get(ip, 0) >= max_per_ip:
                return False
            self._global += 1
            self._per_ip[ip] = self._per_ip.get(ip, 0) + 1
            return True

    def release(self, ip: str) -> None:
        """Mark one in-flight run for *ip* as completed."""
        with self._lock:
            # Decrement per-IP counter; remove the key when it hits zero.
            current = self._per_ip.get(ip, 0)
            if current <= 1:
                self._per_ip.pop(ip, None)
            else:
                self._per_ip[ip] = current - 1
            # Clamp global at zero to guard against double-release bugs.
            self._global = max(0, self._global - 1)

    def reset(self) -> None:
        """Clear all counters — for tests."""
        with self._lock:
            self._global = 0
            self._per_ip.clear()


# Module-level singleton
inflight = InFlightTracker()
