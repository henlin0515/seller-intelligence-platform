"""Business Intelligence V1 — FastMoss TikTok GMV collection for mapped shops."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from seller.fastmoss.client import (
    REQUEST_DELAY_MIN_SEC,
    FastMossAuthError,
    anonymous_session,
    healthcheck,
)
from seller.fastmoss.recent_data import fetch_period_gmv_php
from seller.fastmoss.review import approved_mapping_rows
from seller.intelligence.business_time import business_today
from seller.intelligence.config import USD_PHP_RATE
from seller.intelligence.periods import IntelligencePeriods, resolve_periods

logger = logging.getLogger("seller.intelligence.business.collector")

STATUS_SUCCESS = "success"
STATUS_FETCH_FAILED = "FETCH_FAILED"
STATUS_AUTH = "AUTH"
STATUS_RATE_LIMIT = "RATE_LIMIT"
STATUS_INVALID_RESPONSE = "INVALID_RESPONSE"
STATUS_MISSING_ID = "MISSING_FASTMOSS_ID"


def daily_adgmv_php(period_gmv_php: float, day_count: int) -> float:
    """TikTok ADGMV = period GMV / inclusive day count."""
    if day_count <= 0:
        return 0.0
    return period_gmv_php / day_count


def classify_collect_error(exc: BaseException) -> str:
    """Map exceptions to strict BI status codes (not reused as success)."""
    if isinstance(exc, FastMossAuthError):
        return STATUS_AUTH
    text = str(exc or "").lower()
    if "401" in text or "403" in text or "auth_required" in text or "unauthorized" in text:
        return STATUS_AUTH
    if "429" in text or "rate limit" in text or "retry-after" in text:
        return STATUS_RATE_LIMIT
    if (
        "missing total_info.sale_amount" in text
        or "invalid response" in text
        or "non-json" in text
        or "schema" in text
    ):
        return STATUS_INVALID_RESPONSE
    return STATUS_FETCH_FAILED


def success_snapshot(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Audit-only copy of a prior successful collect (never used as current KPI)."""
    if not isinstance(row, dict) or row.get("status") != STATUS_SUCCESS:
        return None
    return {
        "data_date": row.get("data_date"),
        "fetched_at": row.get("fetched_at"),
        "status": row.get("status"),
        "mtd_gmv_php": row.get("mtd_gmv_php"),
        "m1_gmv_php": row.get("m1_gmv_php"),
        "tiktok_mtd_adgmv_php": row.get("tiktok_mtd_adgmv_php"),
        "tiktok_m1_adgmv_php": row.get("tiktok_m1_adgmv_php"),
        "mtd_start": row.get("mtd_start"),
        "mtd_end": row.get("mtd_end"),
        "m1_start": row.get("m1_start"),
        "m1_end": row.get("m1_end"),
    }


def row_is_fresh_success(row: dict[str, Any] | None, *, today: date) -> bool:
    """True only when status=success and data_date is the business day."""
    if not isinstance(row, dict):
        return False
    if row.get("status") != STATUS_SUCCESS:
        return False
    data_date = str(row.get("data_date") or "").strip()
    return data_date == today.isoformat()


def collect_mapped_shop_tiktok(
    mapping_row: dict[str, Any],
    periods: IntelligencePeriods,
    *,
    delay_sec: float = 0.0,
    session=None,
    data_date: date | None = None,
    previous_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Collect MTD/M-1 GMV for one mapped shop and derive daily ADGMV.

    Strict freshness: only this attempt's successful API mapping populates ADGMV.
    Failures set metrics to null and may attach ``last_successful_snapshot`` for audit.
    """
    shop_id = str(mapping_row.get("shop_id") or "")
    shop_name = str(mapping_row.get("shop_name") or "")
    tiktok_shop_name = str(mapping_row.get("tiktok_shop_name") or "")
    fastmoss_shop_id = str(mapping_row.get("fastmoss_shop_id") or "")
    fastmoss_shop_name = mapping_row.get("fastmoss_shop_name")
    fastmoss_shop_url = (
        f"https://www.fastmoss.com/shop-marketing/detail/{fastmoss_shop_id}"
        if fastmoss_shop_id
        else None
    )
    today = data_date or periods.reference_today or business_today()
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    prior_snap = success_snapshot(previous_row)

    base: dict[str, Any] = {
        "shop_id": shop_id,
        "shop_name": shop_name,
        "tiktok_shop_name": tiktok_shop_name,
        "fastmoss_shop_id": fastmoss_shop_id,
        "fastmoss_shop_name": fastmoss_shop_name,
        "fastmoss_shop_url": fastmoss_shop_url,
        "tiktok_currency": "PHP",
        "data_date": today.isoformat(),
        "fetched_at": fetched_at,
        "status": STATUS_FETCH_FAILED,
        "error": None,
        "mtd_start": periods.mtd.start.isoformat(),
        "mtd_end": periods.mtd.end.isoformat(),
        "m1_start": periods.m1.start.isoformat(),
        "m1_end": periods.m1.end.isoformat(),
        "mtd_day_count": periods.mtd.day_count,
        "m1_day_count": periods.m1.day_count,
        "mtd_gmv_php": None,
        "m1_gmv_php": None,
        "tiktok_mtd_adgmv_php": None,
        "tiktok_m1_adgmv_php": None,
        "mtd_request_url": None,
        "m1_request_url": None,
        "last_successful_snapshot": prior_snap,
    }

    if not fastmoss_shop_id:
        base["status"] = STATUS_MISSING_ID
        base["error"] = "Missing fastmoss_shop_id"
        return base

    try:
        client = session or anonymous_session()
        if delay_sec > 0:
            time.sleep(delay_sec)
        mtd_gmv, mtd_url, client = fetch_period_gmv_php(
            fastmoss_shop_id,
            periods.mtd.start,
            periods.mtd.end,
            session=client,
            prefetch_detail=False,
        )
        if delay_sec > 0:
            time.sleep(delay_sec)
        m1_gmv, m1_url, _client = fetch_period_gmv_php(
            fastmoss_shop_id,
            periods.m1.start,
            periods.m1.end,
            session=client,
            prefetch_detail=False,
        )
        mtd_adgmv = daily_adgmv_php(mtd_gmv, periods.mtd.day_count)
        m1_adgmv = daily_adgmv_php(m1_gmv, periods.m1.day_count)
        base.update(
            {
                "status": STATUS_SUCCESS,
                "error": None,
                "mtd_gmv_php": round(mtd_gmv, 2),
                "m1_gmv_php": round(m1_gmv, 2),
                "tiktok_mtd_adgmv_php": round(mtd_adgmv, 4),
                "tiktok_m1_adgmv_php": round(m1_adgmv, 4),
                "mtd_request_url": mtd_url,
                "m1_request_url": m1_url,
                # Current success replaces audit snapshot for this row.
                "last_successful_snapshot": None,
            }
        )
    except Exception as exc:
        status = classify_collect_error(exc)
        logger.warning(
            "FastMoss collection failed for %s (%s): %s [%s]",
            shop_name,
            shop_id,
            exc,
            status,
        )
        base["status"] = status
        base["error"] = str(exc)
        base["mtd_gmv_php"] = None
        base["m1_gmv_php"] = None
        base["tiktok_mtd_adgmv_php"] = None
        base["tiktok_m1_adgmv_php"] = None

    return base


def collect_all_mapped_shops(
    *,
    reference_today: date | None = None,
    mapping_path: str | None = None,
    delay_sec: float = 0.0,
    run_healthcheck: bool = True,
) -> dict[str, Any]:
    """Collect TikTok GMV for every review-approved FastMoss mapping."""
    today = reference_today or business_today()
    periods = resolve_periods(today)
    mapped_rows = approved_mapping_rows(mapping_path)

    health: dict[str, Any] | None = None
    if run_healthcheck and mapped_rows:
        health = healthcheck()
        if not health.get("ok"):
            logger.error(
                "FastMoss healthcheck FAILED before bulk collect — %s | action=%s",
                health.get("message"),
                health.get("action"),
            )

    sellers: list[dict[str, Any]] = []
    for index, row in enumerate(mapped_rows):
        if index > 0 and delay_sec > 0:
            time.sleep(delay_sec)
        sellers.append(
            collect_mapped_shop_tiktok(
                row,
                periods,
                delay_sec=0,
                session=None,
                data_date=today,
            )
        )

    success = sum(1 for row in sellers if row.get("status") == STATUS_SUCCESS)
    failed = len(sellers) - success

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reference_today": today.isoformat(),
        "periods": periods.as_dict(),
        "usd_php_rate": USD_PHP_RATE,
        "source": "fastmoss_recentData",
        "fastmoss_health": health,
        "summary": {
            "processed": len(sellers),
            "success": success,
            "failed": failed,
            "request_delay_min_sec": REQUEST_DELAY_MIN_SEC,
        },
        "sellers": sellers,
    }
