"""Seller Level Analysis — per-shop FastMoss trend detail (expandable row)."""

from __future__ import annotations

import logging
import os
import time
from datetime import date, timedelta
from typing import Any

from seller.fastmoss.mapping import (
    MAPPING_MAPPED,
    MAPPING_NEED_REVIEW,
    MAPPING_NOT_FOUND,
    load_fastmoss_mapping,
)
from seller.fastmoss.recent_data import fetch_shop_period_metrics

logger = logging.getLogger("seller.intelligence.shop_detail")

UNAVAILABLE_MESSAGE = "No TikTok / FastMoss data available for this shop."
_DETAIL_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_DETAIL_CACHE_TTL_SEC = float(os.getenv("SHOP_DETAIL_CACHE_TTL_SEC", "300"))


def _cache_key(fastmoss_shop_id: str, start: date, end: date) -> str:
    return f"{fastmoss_shop_id}|{start.isoformat()}|{end.isoformat()}"


def _cache_get(key: str) -> dict[str, Any] | None:
    row = _DETAIL_CACHE.get(key)
    if not row:
        return None
    expires_at, payload = row
    if time.time() > expires_at:
        _DETAIL_CACHE.pop(key, None)
        return None
    return payload


def _cache_set(key: str, payload: dict[str, Any]) -> None:
    _DETAIL_CACHE[key] = (time.time() + _DETAIL_CACHE_TTL_SEC, payload)


def resolve_detail_date_range(
    *,
    start_date: date | None,
    end_date: date | None,
    reference_today: date | None = None,
) -> tuple[date, date]:
    """Default to the last 7 inclusive days ending on reference_today."""
    end = end_date or reference_today or date.today()
    start = start_date or (end - timedelta(days=6))
    if end < start:
        raise ValueError("end_date must be on or after start_date")
    return start, end


def _mapping_by_shop_id() -> dict[str, dict[str, Any]]:
    payload = load_fastmoss_mapping()
    return {
        str(row.get("shop_id") or "").strip(): row
        for row in (payload.get("mappings") or [])
        if str(row.get("shop_id") or "").strip()
    }


def shop_detail_available(mapping_row: dict[str, Any] | None, *, platform_source: str = "") -> bool:
    if str(platform_source or "").upper() == "SHOPEE_ONLY":
        return False
    if not mapping_row:
        return False
    status = str(mapping_row.get("mapping_status") or MAPPING_NOT_FOUND).upper()
    if status == MAPPING_NOT_FOUND:
        return False
    fastmoss_id = str(mapping_row.get("fastmoss_shop_id") or "").strip()
    if not fastmoss_id:
        return False
    if status not in {MAPPING_MAPPED, MAPPING_NEED_REVIEW}:
        return False
    return True


def get_shop_detail_payload(
    *,
    shopee_shop_id: str,
    fastmoss_shop_id: str | None = None,
    tiktok_shop_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    platform_source: str = "",
) -> dict[str, Any]:
    """
    Build shop-detail API payload for one Shopee shop row.

    ``tiktok_shop_id`` is accepted for forward compatibility but FastMoss lookup
    uses the mapped ``fastmoss_shop_id``.
    """
    del tiktok_shop_id  # reserved query param; mapping file is source of truth

    shop_id = str(shopee_shop_id or "").strip()
    if not shop_id:
        raise ValueError("shopee_shop_id is required")

    mappings = _mapping_by_shop_id()
    mapping_row = mappings.get(shop_id)
    shop_name = str((mapping_row or {}).get("shop_name") or shop_id)
    start, end = resolve_detail_date_range(start_date=start_date, end_date=end_date)

    base: dict[str, Any] = {
        "shop_id": shop_id,
        "shop_name": shop_name,
        "available": False,
        "message": UNAVAILABLE_MESSAGE,
        "range": {"start_date": start.isoformat(), "end_date": end.isoformat()},
        "metrics": None,
        "fastmoss_shop_id": None,
        "fastmoss_shop_name": None,
    }

    if not shop_detail_available(mapping_row, platform_source=platform_source):
        return base

    resolved_fastmoss_id = str(fastmoss_shop_id or (mapping_row or {}).get("fastmoss_shop_id") or "").strip()
    if not resolved_fastmoss_id:
        return base

    base["fastmoss_shop_id"] = resolved_fastmoss_id
    base["fastmoss_shop_name"] = (mapping_row or {}).get("fastmoss_shop_name")

    cache_key = _cache_key(resolved_fastmoss_id, start, end)
    cached = _cache_get(cache_key)
    if cached:
        return {**base, **cached, "cached": True}

    try:
        metrics, request_url, _session = fetch_shop_period_metrics(resolved_fastmoss_id, start, end)
    except Exception as exc:
        logger.warning("Shop detail fetch failed for %s (%s): %s", shop_id, resolved_fastmoss_id, exc)
        base["available"] = False
        base["message"] = str(exc) or "Could not load FastMoss trend data."
        base["error"] = True
        return base

    result = {
        "available": True,
        "message": None,
        "metrics": metrics,
        "source_url": request_url,
    }
    _cache_set(cache_key, result)
    base.update(result)
    return base
