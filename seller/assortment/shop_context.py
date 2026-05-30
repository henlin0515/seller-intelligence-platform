from __future__ import annotations

import json
from typing import Any

from seller.assortment.db import get_session
from seller.assortment.models import CompetitorProduct, TrackerFetchStatus
from seller.competitor_tracker.sheet import load_competitors_from_sheet


def load_shop_pairs() -> list[dict[str, str]]:
    rows, _meta = load_competitors_from_sheet()
    return rows


def get_shop_meta_map() -> dict[str, dict[str, Any]]:
    """shop_id -> {seller_name, shopee_link, tiktok_link, row_number}."""
    out: dict[str, dict[str, Any]] = {}
    for row in load_shop_pairs():
        sid = row.get("shop_id") or ""
        if not sid:
            continue
        out[sid] = {
            "seller_id": sid,
            "seller_name": row.get("shop_name") or sid,
            "shopee_link": row.get("shopee_link") or "",
            "tiktok_link": row.get("tiktok_link") or "",
            "row_number": row.get("row_number"),
        }
    session = get_session()
    try:
        for status in session.query(TrackerFetchStatus).all():
            if status.seller_id not in out:
                out[status.seller_id] = {
                    "seller_id": status.seller_id,
                    "seller_name": status.seller_name or status.seller_id,
                    "shopee_link": status.shopee_link or "",
                    "tiktok_link": status.tiktok_link or "",
                    "row_number": None,
                }
            else:
                if status.shopee_link:
                    out[status.seller_id]["shopee_link"] = status.shopee_link
                if status.tiktok_link:
                    out[status.seller_id]["tiktok_link"] = status.tiktok_link
            try:
                stored = json.loads(status.link_results_json or "{}")
                if isinstance(stored, dict):
                    out[status.seller_id]["shopee_status"] = stored.get("shopee_status")
                    out[status.seller_id]["tiktok_status"] = stored.get("tiktok_status")
            except json.JSONDecodeError:
                pass
    finally:
        session.close()
    return out


def shop_header(shop_id: str, meta_map: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    meta = (meta_map or get_shop_meta_map()).get(shop_id) or {}
    return {
        "seller_id": shop_id,
        "seller_name": meta.get("seller_name") or shop_id,
        "shopee_link": meta.get("shopee_link") or "NA",
        "tiktok_link": meta.get("tiktok_link") or "NA",
        "row_number": meta.get("row_number"),
    }


def _parse_sku_display(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
    except json.JSONDecodeError:
        pass
    return [raw]


def product_to_dict(p: CompetitorProduct) -> dict[str, Any]:
    return {
        "id": p.id,
        "product_name": p.product_name,
        "product_link": p.product_link,
        "product_image_url": p.product_image_url,
        "sku_variations": _parse_sku_display(p.sku_variations),
        "price": p.price,
        "platform": p.platform,
        "listed_at": p.listed_at.isoformat() if p.listed_at else None,
        "first_detected_at": p.first_detected_at.isoformat() if p.first_detected_at else None,
    }
