"""Assortment Intelligence V1 — TikTok Product Radar."""

from __future__ import annotations

from typing import Any

from seller.intelligence.assortment.radar import build_tiktok_product_radar
from seller.intelligence.seller_master import SellerMasterLoadResult, get_seller_master


def get_assortment_intelligence(
    master: SellerMasterLoadResult | None = None,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Build TikTok Product Radar from Google Sheet seller master + FastMoss catalog."""
    loaded = master or get_seller_master()
    radar = build_tiktok_product_radar(master=loaded, force_refresh=force_refresh)

    return {
        **radar,
        "data_source_label": loaded.data_source,
        "tab": loaded.tab,
        "import": loaded.stats.as_dict(),
        "tracker_connected": False,
        "fastmoss_connected": bool(radar.get("portfolio", {}).get("total_products")),
    }
