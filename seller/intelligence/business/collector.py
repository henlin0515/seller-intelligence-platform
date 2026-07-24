"""Business Intelligence V1 — FastMoss TikTok GMV collection for mapped shops."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from seller.fastmoss.client import REQUEST_DELAY_MIN_SEC, anonymous_session, healthcheck
from seller.fastmoss.recent_data import fetch_period_gmv_php, prefetch_shop_detail
from seller.fastmoss.review import approved_mapping_rows
from seller.intelligence.business_time import business_today
from seller.intelligence.config import USD_PHP_RATE
from seller.intelligence.periods import IntelligencePeriods, resolve_periods

logger = logging.getLogger("seller.intelligence.business.collector")


def daily_adgmv_php(period_gmv_php: float, day_count: int) -> float:
    """TikTok ADGMV = period GMV / inclusive day count."""
    if day_count <= 0:
        return 0.0
    return period_gmv_php / day_count


def collect_mapped_shop_tiktok(
    mapping_row: dict[str, Any],
    periods: IntelligencePeriods,
    *,
    delay_sec: float = 0.0,
    session=None,
) -> dict[str, Any]:
    """
    Collect MTD/M-1 GMV for one mapped shop and derive daily ADGMV.

    Uses anonymous FastMoss sessions by default (login Cookie often trips MSG_SAFE_0001).
    """
    shop_id = str(mapping_row.get("shop_id") or "")
    shop_name = str(mapping_row.get("shop_name") or "")
    tiktok_shop_name = str(mapping_row.get("tiktok_shop_name") or "")
    fastmoss_shop_id = str(mapping_row.get("fastmoss_shop_id") or "")
    fastmoss_shop_name = mapping_row.get("fastmoss_shop_name")

    base: dict[str, Any] = {
        "shop_id": shop_id,
        "shop_name": shop_name,
        "tiktok_shop_name": tiktok_shop_name,
        "fastmoss_shop_id": fastmoss_shop_id,
        "fastmoss_shop_name": fastmoss_shop_name,
        "status": "failed",
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
    }

    try:
        client = prefetch_shop_detail(fastmoss_shop_id, session or anonymous_session())
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
                "status": "success",
                "mtd_gmv_php": round(mtd_gmv, 2),
                "m1_gmv_php": round(m1_gmv, 2),
                "tiktok_mtd_adgmv_php": round(mtd_adgmv, 4),
                "tiktok_m1_adgmv_php": round(m1_adgmv, 4),
                "mtd_request_url": mtd_url,
                "m1_request_url": m1_url,
            }
        )
    except Exception as exc:
        logger.warning("FastMoss collection failed for %s (%s): %s", shop_name, shop_id, exc)
        base["error"] = str(exc)

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
        sellers.append(collect_mapped_shop_tiktok(row, periods, delay_sec=0, session=None))

    success = sum(1 for row in sellers if row.get("status") == "success")
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
