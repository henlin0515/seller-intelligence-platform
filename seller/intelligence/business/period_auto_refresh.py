"""Auto-refresh FastMoss TikTok BI whenever UI MTD / M-1 period tags change."""

from __future__ import annotations

import logging
import os
import threading
import time
from copy import deepcopy
from datetime import date
from typing import Any

from seller.intelligence.business.store import load_business_intelligence_data
from seller.intelligence.periods import periods_match_payload, resolve_periods

logger = logging.getLogger("seller.intelligence.period_auto_refresh")

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "trigger": None,
    "reason": None,
    "target_periods": None,
    "percent": 0,
    "shops_processed": 0,
    "shops_total": 0,
    "success": 0,
    "failed": 0,
    "error": None,
    "result": None,
}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def auto_period_refresh_enabled() -> bool:
    """Controlled by INTELLIGENCE_AUTO_REFRESH_ON_PERIOD_CHANGE (default true)."""
    return _env_bool("INTELLIGENCE_AUTO_REFRESH_ON_PERIOD_CHANGE", True)


def tiktok_bi_periods_stale(*, reference_today: date | None = None) -> tuple[bool, str]:
    """Return (stale, reason) comparing cached BI periods to current UI tags."""
    today = reference_today or date.today()
    current = resolve_periods(today)
    saved = load_business_intelligence_data()
    if not saved:
        return True, "no TikTok BI cache — collect for current MTD/M-1"
    collected = saved.get("periods")
    if periods_match_payload(
        collected if isinstance(collected, dict) else None,
        current,
    ):
        return False, "TikTok BI periods match UI tags"
    return True, "UI MTD/M-1 tags changed — re-collect FastMoss for new ranges"


def get_tiktok_period_refresh_status() -> dict[str, Any]:
    with _lock:
        return deepcopy(_state)


def _set_state(**kwargs: Any) -> None:
    with _lock:
        _state.update(kwargs)


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run_tiktok_period_refresh(
    *,
    reference_today: date | None = None,
    trigger: str = "period_change",
) -> dict[str, Any]:
    """Blocking re-collect of approved FastMoss TikTok GMV for current periods."""
    today = reference_today or date.today()
    periods = resolve_periods(today)
    _set_state(
        running=True,
        started_at=_utc_now(),
        finished_at=None,
        trigger=trigger,
        reason="Collecting FastMoss for current MTD/M-1",
        target_periods=periods.as_dict(),
        percent=5,
        shops_processed=0,
        shops_total=0,
        success=0,
        failed=0,
        error=None,
        result=None,
    )
    try:
        from seller.intelligence.business.bi_cache_refresh import refresh_bi_cache

        result = refresh_bi_cache(reference_today=today, trigger=trigger)
        summary = {
            "success": True,
            "trigger": trigger,
            "periods": periods.as_dict(),
            "approved_count": result.get("approved_count"),
            "tiktok_data_refreshed_count": result.get("tiktok_data_refreshed_count"),
            "collection_success": result.get("collection_success"),
            "updated_count": result.get("updated_count"),
            "elapsed_sec": result.get("elapsed_sec"),
            "cache_overwritten": result.get("cache_overwritten"),
            "bi_date": result.get("bi_date"),
            "finished_at": _utc_now(),
        }
        _set_state(
            running=False,
            finished_at=summary["finished_at"],
            percent=100,
            shops_processed=int(result.get("approved_count") or 0),
            shops_total=int(result.get("approved_count") or 0),
            success=int(result.get("collection_success") or 0),
            failed=max(
                0,
                int(result.get("approved_count") or 0)
                - int(result.get("collection_success") or 0),
            ),
            result=summary,
            reason="TikTok BI refreshed for current period tags",
        )
        logger.info(
            "TikTok period auto-refresh done: success=%s/%s periods=%s",
            summary.get("collection_success"),
            summary.get("approved_count"),
            periods.as_dict(),
        )
        return summary
    except Exception as exc:
        logger.exception("TikTok period auto-refresh failed")
        _set_state(
            running=False,
            finished_at=_utc_now(),
            error=str(exc),
            reason="TikTok period auto-refresh failed",
        )
        raise


def ensure_tiktok_bi_for_current_periods(
    *,
    reference_today: date | None = None,
    trigger: str = "period_change",
    force: bool = False,
) -> dict[str, Any]:
    """
    If UI period tags no longer match cached FastMoss data, start a background
    re-collect for the current MTD / M-1 ranges.

    Safe to call on every /business load — no-ops when data is already aligned
    or a refresh is already running.
    """
    if not auto_period_refresh_enabled() and not force:
        return {
            "started": False,
            "reason": "auto refresh disabled",
            "running": False,
            "periods_stale": False,
        }

    today = reference_today or date.today()
    stale, stale_reason = tiktok_bi_periods_stale(reference_today=today)
    status = get_tiktok_period_refresh_status()

    if status.get("running"):
        return {
            "started": False,
            "reason": "already_running",
            "running": True,
            "periods_stale": True,
            **{k: status.get(k) for k in ("percent", "shops_processed", "shops_total", "target_periods")},
        }

    # Avoid overlapping the heavier full SLA Update Data job.
    try:
        from seller.intelligence.business.sla_refresh import get_sla_refresh_status

        if get_sla_refresh_status().get("running"):
            return {
                "started": False,
                "reason": "sla_refresh_running",
                "running": False,
                "periods_stale": stale,
            }
    except Exception:
        pass

    if not stale and not force:
        return {
            "started": False,
            "reason": stale_reason,
            "running": False,
            "periods_stale": False,
        }

    with _lock:
        if _state.get("running"):
            return {
                "started": False,
                "reason": "already_running",
                "running": True,
                "periods_stale": True,
            }
        _state["running"] = True
        _state["started_at"] = _utc_now()
        _state["trigger"] = trigger
        _state["reason"] = stale_reason
        _state["error"] = None
        _state["result"] = None
        _state["target_periods"] = resolve_periods(today).as_dict()
        _state["percent"] = 1

    def _worker() -> None:
        try:
            run_tiktok_period_refresh(reference_today=today, trigger=trigger)
        except Exception:
            _set_state(
                running=False,
                finished_at=_utc_now(),
                error="TikTok period auto-refresh worker failed",
                reason="TikTok period auto-refresh failed",
            )

    threading.Thread(
        target=_worker,
        name="tiktok-period-auto-refresh",
        daemon=True,
    ).start()
    logger.info("TikTok period auto-refresh queued: %s", stale_reason)
    return {
        "started": True,
        "reason": stale_reason,
        "running": True,
        "periods_stale": True,
        "trigger": trigger,
        "target_periods": resolve_periods(today).as_dict(),
    }
