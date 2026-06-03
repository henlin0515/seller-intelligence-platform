"""Assortment Intelligence V1 — TikTok Product Radar."""

from __future__ import annotations

from typing import Any

from seller.intelligence.assortment.radar import build_tiktok_product_radar
from seller.intelligence.seller_master import SellerMasterLoadResult, get_seller_master


def get_assortment_intelligence(
    master: SellerMasterLoadResult | None = None,
    *,
    force_refresh: bool = False,
    fetch_fastmoss: bool | None = None,
) -> dict[str, Any]:
    """Build TikTok Product Radar from Google Sheet seller master + optional FastMoss catalog."""
    loaded = master or get_seller_master()
    do_fetch = fetch_fastmoss if fetch_fastmoss is not None else force_refresh
    radar = build_tiktok_product_radar(
        master=loaded,
        force_refresh=force_refresh,
        fetch_fastmoss=do_fetch,
    )

    return {
        **radar,
        "data_source_label": loaded.data_source,
        "tab": loaded.tab,
        "import": loaded.stats.as_dict(),
        "tracker_connected": False,
        "fastmoss_connected": bool(radar.get("portfolio", {}).get("total_products")),
    }
