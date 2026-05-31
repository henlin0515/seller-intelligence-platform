"""In-memory login brute-force protection keyed by client IP."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("auth.bruteforce")

_lock = threading.Lock()
_records: dict[str, dict[str, Any]] = {}


@dataclass
class LockoutState:
    locked: bool
    remaining_seconds: int
    failures: int


def _now() -> float:
    return time.time()


def _get_record(ip: str) -> dict[str, Any]:
    rec = _records.get(ip)
    if rec is None:
        rec = {"failures": 0, "locked_until": 0.0}
        _records[ip] = rec
    return rec


def check_lockout(ip: str, *, max_attempts: int, lockout_seconds: int) -> LockoutState:
    with _lock:
        rec = _get_record(ip)
        locked_until = float(rec.get("locked_until") or 0)
        now = _now()
        if locked_until > now:
            return LockoutState(
                locked=True,
                remaining_seconds=int(locked_until - now),
                failures=int(rec.get("failures") or 0),
            )
        if locked_until and locked_until <= now:
            rec["failures"] = 0
            rec["locked_until"] = 0.0
        failures = int(rec.get("failures") or 0)
        if failures >= max_attempts:
            rec["locked_until"] = now + lockout_seconds
            return LockoutState(
                locked=True,
                remaining_seconds=lockout_seconds,
                failures=failures,
            )
        return LockoutState(locked=False, remaining_seconds=0, failures=failures)


def record_failed_attempt(
    ip: str,
    *,
    username: str,
    max_attempts: int,
    lockout_seconds: int,
) -> LockoutState:
    with _lock:
        rec = _get_record(ip)
        now = _now()
        locked_until = float(rec.get("locked_until") or 0)
        if locked_until > now:
            state = LockoutState(
                locked=True,
                remaining_seconds=int(locked_until - now),
                failures=int(rec.get("failures") or 0),
            )
        else:
            rec["failures"] = int(rec.get("failures") or 0) + 1
            failures = rec["failures"]
            if failures >= max_attempts:
                rec["locked_until"] = now + lockout_seconds
                state = LockoutState(
                    locked=True,
                    remaining_seconds=lockout_seconds,
                    failures=failures,
                )
            else:
                state = LockoutState(locked=False, remaining_seconds=0, failures=failures)

    logger.warning(
        "Failed login attempt ip=%s username=%s failures=%s locked=%s",
        ip,
        username or "(empty)",
        state.failures,
        state.locked,
    )
    return state


def clear_attempts(ip: str) -> None:
    with _lock:
        if ip in _records:
            _records[ip] = {"failures": 0, "locked_until": 0.0}
