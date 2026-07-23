"""FastMoss shop keyword search (Philippines). Search only — no GMV / recentData."""

from __future__ import annotations

import logging
import random
import time
from typing import Any

from seller.fastmoss.client import (
    REQUEST_DELAY_SEC,
    REQUEST_TIMEOUT_SEC,
    base_url,
    get_shared_session,
    region,
    request_with_retry,
)

logger = logging.getLogger("seller.fastmoss.search")

SEARCH_PATH = "/api/shop/v3/search"
DEFAULT_BASE_URL = "https://www.fastmoss.com"
DEFAULT_REGION = "PH"
DEFAULT_PAGE_SIZE = 10


def _shop_detail_url(shop_id: str) -> str:
    return f"{base_url()}/shop-marketing/detail/{shop_id}"


def _parse_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    info = row.get("shop_info") if isinstance(row.get("shop_info"), dict) else row
    shop_id = str(info.get("id") or info.get("seller_id") or row.get("seller_id") or "").strip()
    name = str(info.get("name") or info.get("shop_name") or "").strip()
    handle = str(
        info.get("unique_id")
        or info.get("nickname")
        or info.get("nick_name")
        or info.get("seller_name")
        or row.get("unique_id")
        or row.get("nickname")
        or ""
    ).strip()
    if not shop_id or not name:
        return None
    return {
        "fastmoss_shop_id": shop_id,
        "fastmoss_shop_name": name,
        "fastmoss_handle": handle or None,
        "fastmoss_unique_id": str(info.get("unique_id") or row.get("unique_id") or "").strip() or None,
        "fastmoss_shop_url": _shop_detail_url(shop_id),
        "region": str(info.get("region") or row.get("region") or region()).strip(),
        "seller_company": str(
            info.get("company_name")
            or info.get("seller_company")
            or row.get("company_name")
            or row.get("seller_company")
            or ""
        ).strip()
        or None,
        "category": str(
            info.get("category_name")
            or info.get("category")
            or row.get("category_name")
            or row.get("category")
            or ""
        ).strip()
        or None,
        "total_sales": info.get("total_sale_amount")
        or info.get("total_sales")
        or row.get("total_sale_amount")
        or row.get("total_sales"),
        "total_sold": info.get("total_sale_count")
        or info.get("total_sold")
        or row.get("total_sale_count")
        or row.get("total_sold"),
    }


def search_shops(keyword: str, *, page_size: int = DEFAULT_PAGE_SIZE) -> list[dict[str, Any]]:
    """
    Search FastMoss shops by TikTok shop name keyword.

    Uses ``GET /api/shop/v3/search`` (region PH by default).
    """
    query = (keyword or "").strip()
    if not query:
        return []

    params = {
        "words": query,
        "page": "1",
        "pagesize": str(max(1, min(page_size, 20))),
        "order": "1,2",
        "region": region(),
        "_time": str(int(time.time())),
        "cnonce": str(random.randint(10_000_000, 99_999_999)),
    }
    url = f"{base_url()}{SEARCH_PATH}"
    session = get_shared_session()
    try:
        resp = request_with_retry(
            session,
            "GET",
            url,
            params=params,
            headers={"Referer": f"{base_url()}/shop-marketing/search"},
        )
        payload = resp.json()
    except Exception as exc:
        logger.warning("FastMoss search failed for %r: %s", query, exc)
        return []

    if payload.get("code") != 200:
        logger.warning(
            "FastMoss search non-200 code for %r: %s",
            query,
            payload.get("message") or payload.get("msg") or payload.get("code"),
        )
        return []

    rows = (payload.get("data") or {}).get("list") or []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate = _parse_candidate(row)
        if not candidate:
            continue
        sid = candidate["fastmoss_shop_id"]
        if sid in seen:
            continue
        seen.add(sid)
        out.append(candidate)
    return out


def search_shop_candidates(
    keyword: str,
    *,
    tiktok_shop_name: str | None = None,
    page_size: int = 5,
) -> list[dict[str, Any]]:
    """Search FastMoss and return top candidates with confidence vs TikTok name."""
    from seller.fastmoss.match_scoring import candidate_similarity

    query_name = (tiktok_shop_name or keyword or "").strip()
    rows = search_shops(keyword, page_size=max(page_size, 5))[:page_size]
    out: list[dict[str, Any]] = []
    for row in rows:
        confidence = round(candidate_similarity(query_name, row), 4)
        out.append({**row, "confidence": confidence})
    out.sort(key=lambda item: item.get("confidence") or 0, reverse=True)
    return out
