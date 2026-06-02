"""Assortment Intelligence V1 — seller list from shared master (Phase 1)."""

from __future__ import annotations

from typing import Any

from seller.intelligence.seller_master import SellerMasterLoadResult, get_seller_master


def build_assortment_seller_row(record: dict[str, str]) -> dict[str, Any]:
    """Minimal assortment row: master fields only, no product data yet."""
    return {
        "shop_id": record["shop_id"],
        "shop_name": record["shop_name"],
        "shopee_link": record["shopee_link"],
        "tiktok_shop_name": record["tiktok_shop_name"],
        "mapping_status": "unmapped",
        "missing_count": 0,
        "need_review_count": 0,
        "price_gap_risk": False,
        "new_listings_count": 0,
        "tracker_connected": False,
        "fastmoss_connected": False,
        "data_status": "sheet_master",
        "last_synced_at": None,
        "missing_products": [],
        "need_review": [],
    }


def get_assortment_intelligence(
    master: SellerMasterLoadResult | None = None,
) -> dict[str, Any]:
    """Assortment module payload using the same seller master as Business Intelligence."""
    loaded = master or get_seller_master()
    return {
        "module": "assortment_intelligence",
        "version": "v1",
        "status": "sheet_master",
        "data_source": loaded.data_source,
        "tab": loaded.tab,
        "tracker_connected": False,
        "fastmoss_connected": False,
        "sellers": [build_assortment_seller_row(s.as_dict()) for s in loaded.sellers],
        "import": loaded.stats.as_dict(),
    }
