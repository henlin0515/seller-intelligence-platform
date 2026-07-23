"""Safe BI cache refresh — overwrite only on success; preserve previous on failure."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from seller.fastmoss.review import approved_mapping_rows
from seller.intelligence.business.collector import collect_mapped_shop_tiktok
from seller.intelligence.business.store import (
    bi_data_path,
    load_business_intelligence_data,
    save_business_intelligence_data,
)
from seller.intelligence.config import USD_PHP_RATE
from seller.intelligence.periods import IntelligencePeriods, resolve_periods

logger = logging.getLogger("seller.intelligence.bi_cache_refresh")


class BiCacheRefreshError(RuntimeError):
    """Raised when BI refresh fails and the previous cache must be kept."""


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _log_context(periods: IntelligencePeriods, *, bi_date: date) -> str:
    return (
        f"bi_date={bi_date.isoformat()} "
        f"mtd={periods.mtd.start.isoformat()}→{periods.mtd.end.isoformat()} "
        f"m1={periods.m1.start.isoformat()}→{periods.m1.end.isoformat()}"
    )


def build_bi_cache_payload(
    *,
    reference_today: date,
    periods: IntelligencePeriods,
    sellers: list[dict[str, Any]],
) -> dict[str, Any]:
    success = sum(1 for row in sellers if row.get("status") == "success")
    return {
        "generated_at": _utc_now(),
        "reference_today": reference_today.isoformat(),
        "periods": periods.as_dict(),
        "usd_php_rate": USD_PHP_RATE,
        "source": "fastmoss_recentData",
        "summary": {
            "processed": len(sellers),
            "success": success,
            "failed": len(sellers) - success,
            "approved_only": True,
        },
        "sellers": sellers,
    }


def refresh_bi_cache(
    *,
    delay_sec: float = 0.35,
    reference_today: date | None = None,
    trigger: str = "manual",
    collect_fn=None,
) -> dict[str, Any]:
    """
    Re-fetch FastMoss TikTok GMV for all approved mappings using current UI periods.

    On success: atomically overwrite ``business_intelligence_data.json``.
    On failure: leave the previous cache untouched and raise ``BiCacheRefreshError``.
    """
    collect = collect_fn or collect_mapped_shop_tiktok
    today = reference_today or date.today()
    periods = resolve_periods(today)
    started = time.perf_counter()
    ctx = _log_context(periods, bi_date=today)
    cache_path = bi_data_path()
    previous = load_business_intelligence_data()

    logger.info(
        "BI cache refresh START | %s | trigger=%s | cache=%s | had_previous=%s",
        ctx,
        trigger,
        cache_path,
        previous is not None,
    )

    try:
        approved = approved_mapping_rows()
        if not approved:
            elapsed = time.perf_counter() - started
            logger.warning(
                "BI cache refresh SKIPPED (no approved mappings) — preserving previous cache | "
                "%s | updated=0 | elapsed_sec=%.2f | trigger=%s",
                ctx,
                elapsed,
                trigger,
            )
            return {
                "success": True,
                "skipped": True,
                "reason": "no_approved_mappings",
                "cache_overwritten": False,
                "bi_date": today.isoformat(),
                "reference_today": today.isoformat(),
                "periods": periods.as_dict(),
                "approved_count": 0,
                "updated_count": 0,
                "tiktok_data_refreshed_count": 0,
                "collection_success": 0,
                "elapsed_sec": round(elapsed, 2),
                "trigger": trigger,
            }

        sellers: list[dict[str, Any]] = []
        refreshed = 0
        for index, row in enumerate(approved):
            shop_id = str(row.get("shop_id") or "")
            if not shop_id:
                continue
            if index > 0 and delay_sec > 0:
                time.sleep(delay_sec)
            collected = collect(row, periods, delay_sec=0)
            sellers.append(collected)
            if collected.get("status") == "success":
                refreshed += 1

        if refreshed == 0:
            raise BiCacheRefreshError(
                f"All {len(sellers)} FastMoss BI collects failed — preserving previous cache"
            )

        payload = build_bi_cache_payload(
            reference_today=today,
            periods=periods,
            sellers=sellers,
        )
        save_business_intelligence_data(payload)
        elapsed = time.perf_counter() - started

        logger.info(
            "BI cache refresh SUCCESS | %s | updated=%s | success=%s | failed=%s | "
            "elapsed_sec=%.2f | trigger=%s | cache_overwritten=true",
            ctx,
            len(sellers),
            refreshed,
            len(sellers) - refreshed,
            elapsed,
            trigger,
        )
        return {
            "success": True,
            "skipped": False,
            "cache_overwritten": True,
            "bi_date": today.isoformat(),
            "reference_today": today.isoformat(),
            "periods": periods.as_dict(),
            "approved_count": len(approved),
            "updated_count": len(sellers),
            "tiktok_data_refreshed_count": refreshed,
            "collection_success": refreshed,
            "elapsed_sec": round(elapsed, 2),
            "trigger": trigger,
            "generated_at": payload["generated_at"],
            "summary": payload["summary"],
        }
    except Exception as exc:
        elapsed = time.perf_counter() - started
        logger.exception(
            "BI cache refresh FAILED — preserving previous cache | %s | updated=0 | "
            "elapsed_sec=%.2f | trigger=%s | error=%s",
            ctx,
            elapsed,
            trigger,
            exc,
        )
        if isinstance(exc, BiCacheRefreshError):
            raise
        raise BiCacheRefreshError(str(exc)) from exc


def bi_cache_needs_daily_refresh(*, reference_today: date | None = None) -> tuple[bool, str]:
    """True when cache is missing, wrong calendar day, or MTD/M-1 tags drifted."""
    from seller.intelligence.periods import periods_match_payload

    today = reference_today or date.today()
    current = resolve_periods(today)
    saved = load_business_intelligence_data()
    if not saved:
        return True, "BI cache missing"
    if str(saved.get("reference_today") or "") != today.isoformat():
        return True, f"BI cache day {saved.get('reference_today')} != today {today.isoformat()}"
    if not periods_match_payload(
        saved.get("periods") if isinstance(saved.get("periods"), dict) else None,
        current,
    ):
        return True, "BI cache MTD/M-1 periods do not match UI tags"
    return False, "BI cache current for today"
