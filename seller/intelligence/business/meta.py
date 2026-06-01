"""Business Intelligence V1 — mock search/link metadata (not used in formulas)."""

from __future__ import annotations

from typing import Any

from seller.intelligence.business.mock_data import get_mock_business_intelligence

BUSINESS_SELLER_META: dict[str, dict[str, str]] = {
    "100001": {
        "shopee_link": "https://shopee.ph/novastyle.ph",
        "tiktok_shop_name": "NovaStyle Official TT",
    },
    "100002": {
        "shopee_link": "https://shopee.ph/urbanpeak.retail",
        "tiktok_shop_name": "UrbanPeak FastMoss",
    },
    "100003": {
        "shopee_link": "https://shopee.ph/glowmart.official",
        "tiktok_shop_name": "GlowMart TikTok Shop",
    },
    "100004": {
        "shopee_link": "https://shopee.ph/techhive.direct",
        "tiktok_shop_name": "TechHive FM Store",
    },
    "100005": {
        "shopee_link": "https://shopee.ph/homenest.living",
        "tiktok_shop_name": "HomeNest Living TT",
    },
}


def get_mock_business_intelligence_payload() -> list[dict[str, Any]]:
    """Calculated metrics + mock search metadata for UI."""
    rows = get_mock_business_intelligence()
    out: list[dict[str, Any]] = []
    for row in rows:
        meta = BUSINESS_SELLER_META.get(row["shop_id"], {})
        out.append(
            {
                **row,
                "shopee_link": meta.get("shopee_link", ""),
                "tiktok_shop_name": meta.get("tiktok_shop_name", ""),
            }
        )
    return out
