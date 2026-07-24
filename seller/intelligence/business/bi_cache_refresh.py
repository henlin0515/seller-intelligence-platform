"""Safe BI cache refresh — overwrite only on success; preserve previous on failure."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from seller.fastmoss.client import (
    anonymous_session,
    cookie_configured,
    get_last_health,
    healthcheck,
)
from seller.fastmoss.review import approved_mapping_rows
from seller.intelligence.business.collector import (
    STATUS_SUCCESS,
    collect_mapped_shop_tiktok,
    row_is_fresh_success,
    success_snapshot,
)
from seller.intelligence.business.store import (
    bi_data_path,
    load_business_intelligence_data,
    save_business_intelligence_data,
)
from seller.intelligence.business_time import business_today
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
    invalidate_first: bool = False,
) -> dict[str, Any]:
    """
    Re-fetch FastMoss TikTok GMV for all approved mappings using current UI periods.

    Always scrapes with ``resolve_periods(today)`` — the same MTD/M-1 tags shown in UI.
    Does **not** wipe successful ADGMV before collect (default). On period mismatch,
    marks cache refreshing while preserving prior success rows for matching periods.
    Failed shops keep their previous successful metrics when available.
    """
    from seller.intelligence.business.store import (
        CACHE_STATUS_REFRESHING,
        bi_cache_usable_for_periods,
        invalidate_business_intelligence_cache,
    )
    from seller.intelligence.periods import periods_match_payload

    collect = collect_fn or collect_mapped_shop_tiktok
    today = reference_today or business_today()
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

        prev_by_id: dict[str, dict[str, Any]] = {}
        if isinstance(previous, dict):
            for row in previous.get("sellers") or []:
                if not isinstance(row, dict):
                    continue
                sid = str(row.get("shop_id") or "").strip()
                if sid:
                    prev_by_id[sid] = row

        prev_usable = bi_cache_usable_for_periods(previous, periods)
        prev_periods_ok = periods_match_payload(
            previous.get("periods") if isinstance(previous, dict) else None,
            periods,
        ) if previous else False
        # Mid-refresh: keep only *today's* fresh successes visible; never revive stale ADGMV.
        should_mark_refreshing = (not prev_periods_ok) or (
            invalidate_first
            and (
                not prev_usable
                or trigger
                in {
                    "manual",
                    "sla_update",
                    "period_change",
                    "api_ensure",
                    "force",
                    "user_force",
                }
            )
        )
        if should_mark_refreshing:
            preserved = [
                row
                for row in prev_by_id.values()
                if row_is_fresh_success(row, today=today) and prev_periods_ok
            ]
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
                preserve_sellers=preserved,
            )

        health: dict[str, Any] | None = None
        if not skip_healthcheck:
            health = healthcheck()
            if not health.get("ok"):
                action = health.get("action") or "Update FastMoss credentials and retry."
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
        for index, row in enumerate(approved):
            shop_id = str(row.get("shop_id") or "")
            if not shop_id:
                continue
            if index > 0 and delay_sec > 0:
                time.sleep(delay_sec)
            previous_row = prev_by_id.get(shop_id)
            try:
                collected = collect(
                    row,
                    periods,
                    delay_sec=0,
                    session=anonymous_session(),
                    data_date=today,
                    previous_row=previous_row,
                )
            except TypeError:
                # Test doubles / older collect_fn without new kwargs.
                try:
                    collected = collect(row, periods, delay_sec=0, session=anonymous_session())
                except TypeError:
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
                    "fastmoss_shop_id": row.get("fastmoss_shop_id"),
                    "status": "FETCH_FAILED",
                    "error": str(exc),
                    "data_date": today.isoformat(),
                    "fetched_at": _utc_now(),
                    "mtd_gmv_php": None,
                    "m1_gmv_php": None,
                    "tiktok_mtd_adgmv_php": None,
                    "tiktok_m1_adgmv_php": None,
                    "mtd_start": periods.mtd.start.isoformat(),
                    "mtd_end": periods.mtd.end.isoformat(),
                    "m1_start": periods.m1.start.isoformat(),
                    "m1_end": periods.m1.end.isoformat(),
                    "last_successful_snapshot": success_snapshot(previous_row),
                }
            # Guarantee row period tags match UI even if collect_fn is a stub.
            collected.setdefault("mtd_start", periods.mtd.start.isoformat())
            collected.setdefault("mtd_end", periods.mtd.end.isoformat())
            collected.setdefault("m1_start", periods.m1.start.isoformat())
            collected.setdefault("m1_end", periods.m1.end.isoformat())
            collected.setdefault("data_date", today.isoformat())
            collected.setdefault("fetched_at", _utc_now())
            # Strict freshness: never promote prior ADGMV into current fields.
            if collected.get("status") != STATUS_SUCCESS:
                collected["mtd_gmv_php"] = None
                collected["m1_gmv_php"] = None
                collected["tiktok_mtd_adgmv_php"] = None
                collected["tiktok_m1_adgmv_php"] = None
                if "last_successful_snapshot" not in collected:
                    collected["last_successful_snapshot"] = success_snapshot(previous_row)
                collected.pop("preserved_from_previous", None)
            sellers.append(collected)
            if collected.get("status") == STATUS_SUCCESS:
                refreshed += 1
            else:
                failed_shops.append(
                    {
                        "shop_id": shop_id,
                        "shop_name": str(row.get("shop_name") or ""),
                        "status": str(collected.get("status") or "FETCH_FAILED"),
                        "error": str(collected.get("error") or "unknown"),
                    }
                )

        if failed_shops:
            logger.warning(
                "BI cache refresh partial failures | failed=%s | sample=%s",
                len(failed_shops),
                failed_shops[:5],
            )

        success_count = sum(1 for s in sellers if s.get("status") == STATUS_SUCCESS)
        # Always persist this attempt (including failures as null) so UI cannot
        # keep showing yesterday's ADGMV as if it were today's success.
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
                "error_code": health.get("error_code"),
                "message": health.get("message"),
            }
        save_business_intelligence_data(payload)
        try:
            from seller.intelligence.business.sla_update_state import (
                sync_sla_update_state_from_bi,
            )

            sync_sla_update_state_from_bi(
                generated_at=str(payload["generated_at"]),
                reference_today=today.isoformat(),
                tiktok_success=success_count,
            )
        except Exception as sync_exc:
            logger.warning("Could not sync SLA last-updated from BI refresh: %s", sync_exc)
        elapsed = time.perf_counter() - started

        if success_count == 0:
            logger.error(
                "BI cache refresh wrote 0 successes | %s | sellers=%s | trigger=%s",
                ctx,
                len(sellers),
                trigger,
            )
            raise BiCacheRefreshError(
                f"All {len(sellers)} FastMoss BI collects failed — "
                "cache updated with FETCH_FAILED/null ADGMV (no stale fallback)"
            )

        logger.info(
            "BI cache refresh SUCCESS | %s | updated=%s | success=%s | newly_fetched=%s | failed=%s | "
            "elapsed_sec=%.2f | trigger=%s | cache_overwritten=true",
            ctx,
            len(sellers),
            success_count,
            refreshed,
            len(sellers) - success_count,
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
            "collection_success": success_count,
            "collection_failed": len(sellers) - success_count,
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
            "BI cache refresh FAILED — previous cache preserved | %s | updated=0 | "
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

    today = reference_today or business_today()
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
