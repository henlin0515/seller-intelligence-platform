"""Safe BI cache refresh — overwrite only on success; preserve previous on failure."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from seller.fastmoss.client import cookie_configured, get_last_health, get_shared_session, healthcheck
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
        "cache_status": "ready",
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
    delay_sec: float = 0.0,
    reference_today: date | None = None,
    trigger: str = "manual",
    collect_fn=None,
    skip_healthcheck: bool = False,
    invalidate_first: bool = True,
) -> dict[str, Any]:
    """
    Re-fetch FastMoss TikTok GMV for all approved mappings using current UI periods.

    Always scrapes with ``resolve_periods(today)`` — the same MTD/M-1 tags shown in UI.
    When ``invalidate_first`` is True (default), clears stale wrong-period rows before
    collect so the UI never serves June ADGMV under July tags.
    """
    from seller.intelligence.business.store import (
        CACHE_STATUS_REFRESHING,
        bi_cache_usable_for_periods,
        invalidate_business_intelligence_cache,
    )
    from seller.intelligence.periods import periods_match_payload

    collect = collect_fn or collect_mapped_shop_tiktok
    today = reference_today or date.today()
    periods = resolve_periods(today)
    started = time.perf_counter()
    ctx = _log_context(periods, bi_date=today)
    cache_path = bi_data_path()
    previous = load_business_intelligence_data()

    logger.info(
        "BI cache refresh START | %s | trigger=%s | cache=%s | had_previous=%s | cookie=%s",
        ctx,
        trigger,
        cache_path,
        previous is not None,
        cookie_configured(),
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

        # Drop wrong-period cache immediately (or always on Update Data / force refresh).
        prev_usable = bi_cache_usable_for_periods(previous, periods)
        prev_periods_ok = periods_match_payload(
            previous.get("periods") if isinstance(previous, dict) else None,
            periods,
        ) if previous else False
        if invalidate_first and (not prev_usable or not prev_periods_ok or trigger in {
            "manual",
            "sla_update",
            "period_change",
            "api_ensure",
            "force",
            "user_force",
        }):
            invalidate_business_intelligence_cache(
                periods,
                reason=(
                    "period_mismatch"
                    if previous and not prev_periods_ok
                    else "refresh_started"
                ),
                trigger=trigger,
                path=cache_path,
                cache_status=CACHE_STATUS_REFRESHING,
            )

        health: dict[str, Any] | None = None
        if not skip_healthcheck:
            health = healthcheck()
            if not health.get("ok"):
                action = health.get("action") or "Update FASTMOSS_COOKIE and retry."
                logger.error(
                    "BI cache refresh ABORTED — FastMoss healthcheck failed | %s | %s | action=%s",
                    ctx,
                    health.get("message"),
                    action,
                )
                raise BiCacheRefreshError(
                    f"FastMoss healthcheck failed ({health.get('failure_class')}): "
                    f"{health.get('message')}. {action}"
                )

        sellers: list[dict[str, Any]] = []
        refreshed = 0
        failed_shops: list[dict[str, str]] = []
        shared = get_shared_session()
        for index, row in enumerate(approved):
            shop_id = str(row.get("shop_id") or "")
            if not shop_id:
                continue
            if index > 0 and delay_sec > 0:
                time.sleep(delay_sec)
            try:
                collected = collect(row, periods, delay_sec=0, session=shared)
            except TypeError:
                # Test doubles / older collect_fn without session kwarg.
                collected = collect(row, periods, delay_sec=0)
            except Exception as exc:
                logger.warning(
                    "FastMoss BI collect crashed for %s — continuing: %s",
                    shop_id,
                    exc,
                )
                collected = {
                    "shop_id": shop_id,
                    "shop_name": row.get("shop_name"),
                    "status": "failed",
                    "error": str(exc),
                    "mtd_start": periods.mtd.start.isoformat(),
                    "mtd_end": periods.mtd.end.isoformat(),
                    "m1_start": periods.m1.start.isoformat(),
                    "m1_end": periods.m1.end.isoformat(),
                }
            # Guarantee row period tags match UI even if collect_fn is a stub.
            collected.setdefault("mtd_start", periods.mtd.start.isoformat())
            collected.setdefault("mtd_end", periods.mtd.end.isoformat())
            collected.setdefault("m1_start", periods.m1.start.isoformat())
            collected.setdefault("m1_end", periods.m1.end.isoformat())
            sellers.append(collected)
            if collected.get("status") == "success":
                refreshed += 1
            else:
                failed_shops.append(
                    {
                        "shop_id": shop_id,
                        "shop_name": str(row.get("shop_name") or ""),
                        "error": str(collected.get("error") or "unknown"),
                    }
                )

        if failed_shops:
            logger.warning(
                "BI cache refresh partial failures | failed=%s | sample=%s",
                len(failed_shops),
                failed_shops[:5],
            )

        if refreshed == 0:
            raise BiCacheRefreshError(
                f"All {len(sellers)} FastMoss BI collects failed — "
                "cache left invalidated for current UI periods (old wrong-period data not restored)"
            )

        payload = build_bi_cache_payload(
            reference_today=today,
            periods=periods,
            sellers=sellers,
        )
        if health:
            payload["fastmoss_health"] = {
                "ok": health.get("ok"),
                "checked_at": health.get("checked_at"),
                "cookie_configured": health.get("cookie_configured"),
                "message": health.get("message"),
            }
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
            "collection_failed": len(sellers) - refreshed,
            "failed_shops": failed_shops[:20],
            "elapsed_sec": round(elapsed, 2),
            "trigger": trigger,
            "generated_at": payload["generated_at"],
            "summary": payload["summary"],
            "fastmoss_health": health or get_last_health(),
        }
    except Exception as exc:
        elapsed = time.perf_counter() - started
        logger.exception(
            "BI cache refresh FAILED — wrong-period cache not restored | %s | updated=0 | "
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
    from seller.intelligence.business.store import bi_cache_usable_for_periods

    today = reference_today or date.today()
    current = resolve_periods(today)
    saved = load_business_intelligence_data()
    if not saved:
        return True, "BI cache missing"
    if not bi_cache_usable_for_periods(saved, current):
        status = str(saved.get("cache_status") or "")
        if status in {"invalidated", "refreshing"}:
            return True, f"BI cache {status} — needs re-collect for current MTD/M-1"
        if str(saved.get("reference_today") or "") != today.isoformat():
            return True, f"BI cache day {saved.get('reference_today')} != today {today.isoformat()}"
        return True, "BI cache MTD/M-1 periods do not match UI tags or has no success rows"
    return False, "BI cache current for today"
