"""FastMoss shop product catalog (/api/shop/v3/goods)."""

from __future__ import annotations

import logging
import random
import re
import time
from typing import Any

import requests

from seller.fastmoss.recent_data import (
    REQUEST_DELAY_SEC,
    REQUEST_TIMEOUT_SEC,
    _base_url,
    _detail_referer,
    _region,
    prefetch_shop_detail,
)

logger = logging.getLogger("seller.fastmoss.goods")

GOODS_PATH = "/api/shop/v3/goods"
DEFAULT_PAGE_SIZE = 5
DEFAULT_MAX_PAGES = 20


def _parse_price_php(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace("₱", "").strip()
    match = re.search(r"[\d.]+", text)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def parse_fastmoss_product(row: dict[str, Any]) -> dict[str, Any] | None:
    name = str(row.get("title") or row.get("product_name") or "").strip()
    if not name:
        return None
    product_id = str(row.get("product_id") or row.get("id") or "").strip()
    image = str(row.get("img") or row.get("cover") or row.get("image") or "").strip()
    link = str(row.get("detail_url") or row.get("product_link") or "").strip()
    if not link and product_id:
        link = f"https://shop.tiktok.com/view/product/{product_id}?region=PH&local=en"
    price = _parse_price_php(row.get("price"))
    if price is None:
        price = _parse_price_php(row.get("real_price") or row.get("min_price"))
    sold_count = row.get("sold_count")
    try:
        sold_count = int(sold_count) if sold_count is not None else None
    except (TypeError, ValueError):
        sold_count = None
    sale_amount = row.get("sale_amount")
    try:
        sale_amount = float(sale_amount) if sale_amount is not None else None
    except (TypeError, ValueError):
        sale_amount = None
    listed_date = str(row.get("ctime") or row.get("listed_date") or "").strip() or None
    category = ""
    for key in ("category_name_l3", "category_name_l2", "category_name", "category_name_l1"):
        raw_cat = row.get(key)
        if isinstance(raw_cat, list) and raw_cat:
            category = str(raw_cat[0]).strip()
            break
        if isinstance(raw_cat, str) and raw_cat.strip():
            category = raw_cat.strip()
            break
    shop_name = str(row.get("shop_name") or (row.get("shop_info") or {}).get("name") or "").strip() or None

    def _as_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _as_float(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    return {
        "product_id": product_id or None,
        "product_name": name[:512],
        "product_image": image or None,
        "product_price_php": price,
        "product_link": link or None,
        "sold_count": sold_count,
        "sales_amount": sale_amount,
        "listed_date": listed_date,
        "upload_date": listed_date,
        "category": category or None,
        "shop_name": shop_name,
        "relate_video_count": _as_int(row.get("relate_video_count")),
        "relate_live_count": _as_int(row.get("relate_live_count")),
        "relate_author_count": _as_int(row.get("relate_author_count")),
        "inc_sold_count": _as_int(row.get("inc_sold_count")),
        "inc_sale_amount": _as_float(row.get("inc_sale_amount")),
        "source": "fastmoss",
    }


def fetch_shop_goods_page(
    fastmoss_shop_id: str,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    date_type: int = -1,
    order: str = "1,2",
    session: requests.Session | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], requests.Session]:
    shop_id = str(fastmoss_shop_id or "").strip()
    if not shop_id:
        raise ValueError("fastmoss_shop_id is required")

    client = session or prefetch_shop_detail(shop_id)
    params = {
        "id": shop_id,
        "region": _region(),
        "page": int(page),
        "pagesize": int(page_size),
        "date_type": int(date_type),
        "order": order,
        "_time": str(int(time.time())),
        "cnonce": str(random.randint(10_000_000, 99_999_999)),
    }
    url = f"{_base_url()}{GOODS_PATH}"
    resp = client.get(url, params=params, headers={"referer": _detail_referer(shop_id)}, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    payload: dict[str, Any] = resp.json()
    code = payload.get("code")
    if code not in (200, "200"):
        message = payload.get("message") or payload.get("msg") or code
        raise RuntimeError(f"FastMoss goods error: {message}")

    data = payload.get("data") or {}
    raw_rows = data.get("product_list") or []
    products: list[dict[str, Any]] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        parsed = parse_fastmoss_product(row)
        if parsed:
            products.append(parsed)
    meta = {
        "page": page,
        "page_size": page_size,
        "result_cnt": data.get("result_cnt"),
        "total_cnt": data.get("total_cnt") or data.get("total"),
        "request_url": resp.url,
    }
    return products, meta, client


def fetch_shop_goods_catalog(
    fastmoss_shop_id: str,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    page_size: int = DEFAULT_PAGE_SIZE,
    date_type: int = -1,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Paginate FastMoss shop goods catalog."""
    shop_id = str(fastmoss_shop_id or "").strip()
    client = prefetch_shop_detail(shop_id, session)
    all_products: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_cnt = None
    last_url = None

    for page in range(1, max(1, max_pages) + 1):
        rows, meta, client = fetch_shop_goods_page(
            shop_id,
            page=page,
            page_size=page_size,
            date_type=date_type,
            session=client,
        )
        total_cnt = meta.get("total_cnt") if meta.get("total_cnt") is not None else total_cnt
        last_url = meta.get("request_url") or last_url
        if not rows:
            break
        for row in rows:
            key = row.get("product_id") or row.get("product_link") or row.get("product_name")
            if not key or key in seen:
                continue
            seen.add(str(key))
            all_products.append(row)
        if total_cnt is not None and len(all_products) >= int(total_cnt):
            break
        time.sleep(REQUEST_DELAY_SEC)

    return {
        "status": "ok" if all_products else "empty",
        "products": all_products,
        "product_count": len(all_products),
        "total_cnt": total_cnt,
        "pages_fetched": page if all_products else 0,
        "request_url": last_url,
        "source": "fastmoss_goods",
    }
