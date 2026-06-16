"""FastMoss shop recentData — period GMV from total_info.sale_amount."""

from __future__ import annotations

import logging
import os
import random
import time
from datetime import date
from typing import Any

import requests

from seller.fastmoss.search import DEFAULT_BASE_URL, DEFAULT_REGION, REQUEST_TIMEOUT_SEC

logger = logging.getLogger("seller.fastmoss.recent_data")

RECENT_DATA_PATH = "/api/shop/v3/recentData"
REQUEST_DELAY_SEC = float(os.getenv("FASTMOSS_REQUEST_DELAY_SEC", "0.35"))


def _base_url() -> str:
    return (os.getenv("FASTMOSS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _region() -> str:
    return (os.getenv("FASTMOSS_REGION") or DEFAULT_REGION).strip().upper() or DEFAULT_REGION


def _detail_referer(shop_id: str) -> str:
    return f"{_base_url()}/shop-marketing/detail/{shop_id}"


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "lang": "EN_US",
            "region": _region(),
            "source": "pc",
        }
    )
    return session


def prefetch_shop_detail(
    fastmoss_shop_id: str,
    session: requests.Session | None = None,
) -> requests.Session:
    """
    Visit shop detail page to satisfy FastMoss view quota.

    Returns the session carrying detail-page cookies for subsequent API calls.
    """
    shop_id = str(fastmoss_shop_id or "").strip()
    if not shop_id:
        raise ValueError("fastmoss_shop_id is required")
    client = session or _new_session()
    url = _detail_referer(shop_id)
    resp = client.get(url, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    return client


def parse_period_metrics(total_info: dict[str, Any]) -> dict[str, int | float]:
    """Map FastMoss recentData total_info to SLA shop-detail metrics."""
    return {
        "sales_volume": int(total_info.get("sold_count") or 0),
        "sales_amount": round(float(total_info.get("sale_amount") or 0), 2),
        "creator_count": int(total_info.get("author_count") or 0),
        "live_count": int(total_info.get("live_count") or 0),
        "video_count": int(total_info.get("aweme_count") or 0),
        "active_product_count": int(total_info.get("sold_product_count") or 0),
    }


def fetch_recent_data(
    fastmoss_shop_id: str,
    start: date,
    end: date,
    *,
    session: requests.Session | None = None,
    prefetch_detail: bool = True,
) -> tuple[dict[str, Any], str, requests.Session]:
    """
    Fetch recentData for a FastMoss shop and date range.

    Returns ({"total_info": ..., "trend": [...]}, request_url, session).
    """
    shop_id = str(fastmoss_shop_id or "").strip()
    if not shop_id:
        raise ValueError("fastmoss_shop_id is required")
    if end < start:
        raise ValueError("end_date must be on or after start_date")

    client = prefetch_shop_detail(shop_id, session) if prefetch_detail else (session or _new_session())

    params = {
        "id": shop_id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "region": _region(),
        "_time": str(int(time.time())),
        "cnonce": str(random.randint(10_000_000, 99_999_999)),
    }
    url = f"{_base_url()}{RECENT_DATA_PATH}"
    headers = {"referer": _detail_referer(shop_id)}
    resp = client.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    payload: dict[str, Any] = resp.json()
    if payload.get("code") != 200:
        message = payload.get("message") or payload.get("msg") or payload.get("code")
        raise RuntimeError(f"FastMoss recentData error: {message}")

    data = payload.get("data") or {}
    lst = data.get("list") or {}
    return {
        "total_info": lst.get("total_info") or {},
        "trend": lst.get("trend") or [],
    }, resp.url, client


def fetch_shop_period_metrics(
    fastmoss_shop_id: str,
    start: date,
    end: date,
    *,
    session: requests.Session | None = None,
    prefetch_detail: bool = True,
) -> tuple[dict[str, int | float], str, requests.Session]:
    """Fetch period shop trend metrics from recentData total_info."""
    recent, request_url, client = fetch_recent_data(
        fastmoss_shop_id,
        start,
        end,
        session=session,
        prefetch_detail=prefetch_detail,
    )
    return parse_period_metrics(recent.get("total_info") or {}), request_url, client


def fetch_period_gmv_php(
    fastmoss_shop_id: str,
    start: date,
    end: date,
    *,
    session: requests.Session | None = None,
    prefetch_detail: bool = True,
) -> tuple[float, str, requests.Session]:
    """
    Fetch period GMV (PHP) from recentData total_info.sale_amount.

    Returns (sale_amount_php, request_url, session).
    """
    metrics, request_url, client = fetch_shop_period_metrics(
        fastmoss_shop_id,
        start,
        end,
        session=session,
        prefetch_detail=prefetch_detail,
    )
    sale_amount = metrics.get("sales_amount")
    if sale_amount is None:
        raise RuntimeError("FastMoss recentData missing total_info.sale_amount")
    return float(sale_amount), request_url, client
