"""Fetch April/May TikTok GMV from FastMoss recentData sale_amount."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from seller.fastmoss.recent_data import REQUEST_DELAY_SEC, fetch_period_gmv_php, prefetch_shop_detail

logger = logging.getLogger("seller.intelligence.historical_sob.collector")

APRIL_START = date(2026, 4, 1)
APRIL_END = date(2026, 4, 30)
MAY_START = date(2026, 5, 1)
MAY_END = date(2026, 5, 31)


def fetch_shop_historical_tiktok_gmv(
    fastmoss_shop_id: str,
    *,
    delay_sec: float = REQUEST_DELAY_SEC,
) -> dict[str, Any]:
    """Return April/May full-month sale_amount (PHP) for one FastMoss shop."""
    shop_id = str(fastmoss_shop_id or "").strip()
    if not shop_id:
        raise ValueError("fastmoss_shop_id is required")

    session = prefetch_shop_detail(shop_id)
    if delay_sec > 0:
        time.sleep(delay_sec)

    april_gmv, april_url, session = fetch_period_gmv_php(
        shop_id,
        APRIL_START,
        APRIL_END,
        session=session,
        prefetch_detail=False,
    )
    if delay_sec > 0:
        time.sleep(delay_sec)

    may_gmv, may_url, _session = fetch_period_gmv_php(
        shop_id,
        MAY_START,
        MAY_END,
        session=session,
        prefetch_detail=False,
    )

    return {
        "fastmoss_shop_id": shop_id,
        "april_gmv_php": round(float(april_gmv), 2),
        "may_gmv_php": round(float(may_gmv), 2),
        "april_request_url": april_url,
        "may_request_url": may_url,
        "status": "success",
        "error": None,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
