"""Assortment Intelligence V1 — TikTok Product Radar (FastMoss only)."""

from __future__ import annotations

from typing import Any

from seller.intelligence.assortment.radar import build_tiktok_product_radar
from seller.intelligence.seller_master import SellerMasterLoadResult, get_seller_master


def get_assortment_intelligence(
    master: SellerMasterLoadResult | None = None,
) -> dict[str, Any]:
    """Build FastMoss-only TikTok Product Radar payload."""
    loaded = master or get_seller_master()
    radar = build_tiktok_product_radar()
    return {
        **radar,
        "data_source": loaded.data_source,
        "tab": loaded.tab,
        "import": loaded.stats.as_dict(),
        "tracker_connected": False,
        "fastmoss_connected": bool(radar.get("portfolio", {}).get("total_products")),
    }
