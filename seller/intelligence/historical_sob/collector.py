"""Fetch May/June TikTok GMV from FastMoss recentData sale_amount."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from seller.fastmoss.recent_data import REQUEST_DELAY_SEC, fetch_period_gmv_php, prefetch_shop_detail

logger = logging.getLogger("seller.intelligence.historical_sob.collector")

MAY_START = date(2026, 5, 1)
MAY_END = date(2026, 5, 31)
JUNE_START = date(2026, 6, 1)
JUNE_END = date(2026, 6, 30)


def fetch_shop_historical_tiktok_gmv(
    fastmoss_shop_id: str,
    *,
    delay_sec: float = REQUEST_DELAY_SEC,
) -> dict[str, Any]:
    """Return May/June full-month sale_amount (PHP) for one FastMoss shop."""
    shop_id = str(fastmoss_shop_id or "").strip()
    if not shop_id:
        raise ValueError("fastmoss_shop_id is required")

    session = prefetch_shop_detail(shop_id)
    if delay_sec > 0:
        time.sleep(delay_sec)

    may_gmv, may_url, session = fetch_period_gmv_php(
        shop_id,
        MAY_START,
        MAY_END,
        session=session,
        prefetch_detail=False,
    )
    if delay_sec > 0:
        time.sleep(delay_sec)

    june_gmv, june_url, _session = fetch_period_gmv_php(
        shop_id,
        JUNE_START,
        JUNE_END,
        session=session,
        prefetch_detail=False,
    )

    return {
        "fastmoss_shop_id": shop_id,
        "may_gmv_php": round(float(may_gmv), 2),
        "june_gmv_php": round(float(june_gmv), 2),
        "may_request_url": may_url,
        "june_request_url": june_url,
        "period_key": "2026-05_2026-06",
        "status": "success",
        "error": None,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
