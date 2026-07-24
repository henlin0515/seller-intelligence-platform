"""Daily BI cache scheduler — refreshes FastMoss TikTok BI without manual Update Data."""

from __future__ import annotations

import logging
import os
import threading
import time
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Any

from seller.intelligence.business_time import business_today

logger = logging.getLogger("seller.intelligence.bi_daily_scheduler")

_lock = threading.Lock()
_started = False
_state: dict[str, Any] = {
    "enabled": False,
    "running": False,
    "started_at": None,
    "last_run_at": None,
    "last_result": None,
    "next_run_at": None,
    "error": None,
}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def daily_bi_refresh_enabled() -> bool:
    """Controlled by BI_DAILY_REFRESH_ENABLED (default true)."""
    return _env_bool("BI_DAILY_REFRESH_ENABLED", True)


def _refresh_hour_utc() -> int:
    try:
        return max(0, min(23, int(os.getenv("BI_DAILY_REFRESH_HOUR_UTC", "16"))))
    except ValueError:
        return 16


def _refresh_minute_utc() -> int:
    try:
        return max(0, min(59, int(os.getenv("BI_DAILY_REFRESH_MINUTE_UTC", "5"))))
    except ValueError:
        return 5


def next_daily_run_utc(now: datetime | None = None) -> datetime:
    """Next scheduled run in UTC (default 16:05 UTC ≈ 00:05 Asia/Manila)."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    candidate = current.replace(
        hour=_refresh_hour_utc(),
        minute=_refresh_minute_utc(),
        second=0,
        microsecond=0,
    )
    if candidate <= current:
        candidate = candidate + timedelta(days=1)
    return candidate


def get_bi_daily_scheduler_status() -> dict[str, Any]:
    with _lock:
        out = deepcopy(_state)
    out["enabled"] = daily_bi_refresh_enabled()
    out["hour_utc"] = _refresh_hour_utc()
    out["minute_utc"] = _refresh_minute_utc()
    return out


def _set_state(**kwargs: Any) -> None:
    with _lock:
        _state.update(kwargs)


def run_daily_bi_cache_refresh(*, trigger: str = "daily_cron") -> dict[str, Any]:
    """Run one BI cache refresh for today's MTD/M-1 (blocking)."""
    from seller.intelligence.business.bi_cache_refresh import refresh_bi_cache

    _set_state(running=True, error=None)
    try:
        result = refresh_bi_cache(trigger=trigger, reference_today=business_today())
        _set_state(
            running=False,
            last_run_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            last_result=result,
            error=None,
        )
        return result
    except Exception as exc:
        _set_state(
            running=False,
            last_run_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            error=str(exc),
        )
        raise


def maybe_refresh_bi_cache_if_stale(*, trigger: str = "startup_check") -> dict[str, Any]:
    """If BI cache is not for today / current periods, refresh now (blocking)."""
    from seller.intelligence.business.bi_cache_refresh import (
        bi_cache_needs_daily_refresh,
        refresh_bi_cache,
    )

    needs, reason = bi_cache_needs_daily_refresh()
    if not needs:
        logger.info("Daily BI check: %s", reason)
        return {"started": False, "reason": reason, "success": True}
    logger.info("Daily BI check needs refresh: %s", reason)
    result = refresh_bi_cache(trigger=trigger)
    return {"started": True, "reason": reason, **result}


def start_bi_daily_scheduler() -> bool:
    """
    Start background thread that refreshes BI cache once per day.

    Also runs an immediate refresh when cache is missing or not aligned to today.
    """
    global _started
    if not daily_bi_refresh_enabled():
        logger.info("BI daily refresh scheduler disabled")
        return False

    with _lock:
        if _started:
            return False
        _started = True
        _state["enabled"] = True
        _state["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _state["next_run_at"] = next_daily_run_utc().isoformat()

    def _worker() -> None:
        # Startup catch-up (stale day / periods) after a short delay.
        delay = float(os.getenv("BI_DAILY_REFRESH_STARTUP_DELAY_SEC", "8"))
        time.sleep(delay)
        try:
            maybe_refresh_bi_cache_if_stale(trigger="startup_daily_check")
        except Exception:
            logger.exception("Startup BI cache refresh failed — previous cache preserved")

        while True:
            try:
                nxt = next_daily_run_utc()
                _set_state(next_run_at=nxt.isoformat())
                sleep_sec = max(5.0, (nxt - datetime.now(timezone.utc)).total_seconds())
                logger.info(
                    "BI daily scheduler sleeping %.0fs until %s",
                    sleep_sec,
                    nxt.isoformat(),
                )
                time.sleep(sleep_sec)
                run_daily_bi_cache_refresh(trigger="daily_cron")
            except Exception:
                logger.exception("BI daily cron refresh failed — previous cache preserved")
                # Avoid tight crash loops.
                time.sleep(60)

    threading.Thread(target=_worker, name="bi-daily-scheduler", daemon=True).start()
    logger.info(
        "BI daily scheduler started (UTC %02d:%02d)",
        _refresh_hour_utc(),
        _refresh_minute_utc(),
    )
    return True
