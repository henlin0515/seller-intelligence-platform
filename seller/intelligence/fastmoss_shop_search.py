"""FastMoss Shop Search page service."""

from __future__ import annotations

import logging
import os
import time
from datetime import date
from typing import Any

from seller.fastmoss.match_scoring import candidate_similarity, normalize_name
from seller.fastmoss.recent_data import fetch_recent_data
from seller.fastmoss.search import search_shops_or_raise
from seller.intelligence.business.collector import classify_collect_error
from seller.intelligence.business_time import business_today

logger = logging.getLogger("seller.intelligence.fastmoss_shop_search")

SEARCH_TTL_SEC = float(os.getenv("FASTMOSS_SHOP_SEARCH_CACHE_TTL_SEC", "1800"))
DETAIL_TTL_SEC = float(os.getenv("FASTMOSS_SHOP_DETAIL_CACHE_TTL_SEC", "1800"))

_SEARCH_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_DETAIL_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_get(cache: dict[str, tuple[float, dict[str, Any]]], key: str) -> dict[str, Any] | None:
    row = cache.get(key)
    if not row:
        return None
    expires_at, payload = row
    if time.time() > expires_at:
        cache.pop(key, None)
        return None
    return payload


def _cache_set(
    cache: dict[str, tuple[float, dict[str, Any]]], key: str, payload: dict[str, Any], ttl_sec: float
) -> dict[str, Any]:
    cache[key] = (time.time() + ttl_sec, payload)
    return payload


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _coerce_number(value: Any) -> int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        text = str(value).replace(",", "").strip()
        if not text:
            return None
        return float(text) if "." in text else int(text)
    except (TypeError, ValueError):
        return None


def _score_label(query: str, candidate: dict[str, Any], score: float) -> str:
    q = normalize_name(query)
    name = normalize_name(str(candidate.get("fastmoss_shop_name") or ""))
    handle = normalize_name(str(candidate.get("fastmoss_handle") or ""))
    if q and (q == name or q == handle):
        return "Exact Match"
    if score >= 0.82:
        return "High Confidence"
    return "Possible Match"


def _latest_data_date(candidate: dict[str, Any]) -> date:
    raw = str(candidate.get("last_data_date") or candidate.get("lastDataDate") or "").strip()[:10]
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return business_today()


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _candidate_brief(candidate: dict[str, Any], *, query: str) -> dict[str, Any]:
    score = round(candidate_similarity(query, candidate), 4)
    return {
        "shopName": candidate.get("fastmoss_shop_name"),
        "shopId": candidate.get("fastmoss_shop_id"),
        "region": candidate.get("region_name") or candidate.get("region"),
        "category": candidate.get("category"),
        "shopLogo": candidate.get("shop_logo"),
        "followers": _coerce_number(candidate.get("followers")),
        "totalProducts": _coerce_number(candidate.get("product_count")),
        "activeProducts": None,
        "totalSales": _coerce_number(candidate.get("total_sales")),
        "totalGmv": _coerce_number(candidate.get("total_gmv")),
        "currency": candidate.get("currency") or "PHP",
        "shopUrl": candidate.get("fastmoss_shop_url"),
        "lastDataDate": candidate.get("last_data_date"),
        "matchScore": score,
        "matchLabel": _score_label(query, candidate, score),
    }


def search_fastmoss_shops(query: str, *, limit: int = 10) -> dict[str, Any]:
    q = str(query or "").strip()
    if not q:
        return {"query": "", "results": []}
    cache_key = q.lower()
    cached = _cache_get(_SEARCH_CACHE, cache_key)
    if cached:
        return {**cached, "cached": True}
    rows = search_shops_or_raise(q, page_size=max(10, min(limit, 10)))
    ranked = [_candidate_brief(row, query=q) for row in rows[:limit]]
    ranked.sort(key=lambda item: (float(item.get("matchScore") or 0), str(item.get("shopName") or "")), reverse=True)
    payload = {"query": q, "results": ranked[:limit], "cached": False, "lastUpdatedAt": _now_iso()}
    return _cache_set(_SEARCH_CACHE, cache_key, payload, SEARCH_TTL_SEC)


def _resolve_candidate(shop_id: str, shop_name: str | None = None) -> dict[str, Any] | None:
    sid = str(shop_id or "").strip()
    if not sid:
        return None
    for _, cache_row in list(_SEARCH_CACHE.items()):
        if not isinstance(cache_row, tuple) or len(cache_row) != 2:
            continue
        _expires_at, payload = cache_row
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            continue
        for row in results:
            if str(row.get("shopId") or "").strip() == sid:
                return row
    query = str(shop_name or sid).strip()
    if not query:
        return None
    fresh = search_fastmoss_shops(query, limit=10)
    for row in fresh.get("results") or []:
        if str(row.get("shopId") or "").strip() == sid:
            return row
    return None


def get_fastmoss_shop_detail(
    *,
    shop_id: str,
    shop_name: str | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    sid = str(shop_id or "").strip()
    if not sid:
        raise ValueError("shop_id is required")
    cache_key = sid
    if not force_refresh:
        cached = _cache_get(_DETAIL_CACHE, cache_key)
        if cached:
            return {**cached, "cached": True}

    candidate = _resolve_candidate(sid, shop_name)
    end_date = _latest_data_date(candidate or {"last_data_date": business_today().isoformat()})
    start_date = _month_start(end_date)
    elapsed_days = max(0, end_date.day)

    payload: dict[str, Any] = {
        "shopName": (candidate or {}).get("shopName") or shop_name,
        "shopId": sid,
        "shopUrl": (candidate or {}).get("shopUrl"),
        "region": (candidate or {}).get("region"),
        "category": (candidate or {}).get("category"),
        "shopLogo": (candidate or {}).get("shopLogo"),
        "followers": (candidate or {}).get("followers"),
        "totalProducts": (candidate or {}).get("totalProducts"),
        "activeProducts": None,
        "totalSales": (candidate or {}).get("totalSales"),
        "totalGmv": (candidate or {}).get("totalGmv"),
        "mtdSales": None,
        "mtdOrders": None,
        "elapsedDays": elapsed_days,
        "mtdAdg": None,
        "lastDataDate": end_date.isoformat(),
        "lastUpdatedAt": _now_iso(),
        "currency": (candidate or {}).get("currency") or "PHP",
        "mainCategory": (candidate or {}).get("category"),
        "mtdPeriod": {"startDate": start_date.isoformat(), "endDate": end_date.isoformat()},
        "apiStatus": "SUCCESS",
        "errorMessage": None,
        "cached": False,
    }

    try:
        recent, _request_url, _session = fetch_recent_data(sid, start_date, end_date, prefetch_detail=False)
        total_info = recent.get("total_info") or {}
        mtd_sales = _coerce_number(total_info.get("sale_amount"))
        mtd_orders = _coerce_number(total_info.get("sold_count"))
        payload.update(
            {
                "shopName": payload.get("shopName") or total_info.get("shop_name"),
                "region": payload.get("region") or total_info.get("region_name") or total_info.get("region"),
                "currency": payload.get("currency") or total_info.get("currency") or "PHP",
                "followers": payload.get("followers"),
                "totalProducts": payload.get("totalProducts"),
                "activeProducts": _coerce_number(total_info.get("sold_product_count")),
                "mtdSales": mtd_sales,
                "mtdOrders": mtd_orders,
                "mtdAdg": round(float(mtd_sales) / elapsed_days, 4) if mtd_sales is not None and elapsed_days > 0 else None,
                "mtdTrendCreators": _coerce_number(total_info.get("author_count")),
                "mtdTrendLives": _coerce_number(total_info.get("live_count")),
                "mtdTrendVideos": _coerce_number(total_info.get("aweme_count")),
            }
        )
    except Exception as exc:
        status = classify_collect_error(exc)
        payload["apiStatus"] = status
        payload["errorMessage"] = str(exc)
        logger.warning("FastMoss shop detail failed for %s: %s", sid, exc)

    logger.debug("FastMoss shop detail payload for %s: %s", sid, payload)
    return _cache_set(_DETAIL_CACHE, cache_key, payload, DETAIL_TTL_SEC)
