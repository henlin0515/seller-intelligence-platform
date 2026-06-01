"""Assortment Intelligence V1 — realistic mock product-level data (UI only)."""

from __future__ import annotations

from typing import Any

from seller.intelligence.business.mock_data import MOCK_BUSINESS_INPUTS


def _img(seed: str) -> str:
    return f"https://picsum.photos/seed/si-{seed}/120/120"


def _missing(
    pid: str,
    name: str,
    price_php: float,
    confidence: float,
) -> dict[str, Any]:
    return {
        "product_id": pid,
        "image_url": _img(pid),
        "product_name": name,
        "tiktok_link": f"https://www.tiktok.com/view/product/{pid}",
        "price_php": price_php,
        "reason": "Not found on Shopee",
        "confidence_score": confidence,
    }


def _review(
    rid: str,
    shopee_name: str,
    tiktok_name: str,
    similarity: float,
) -> dict[str, Any]:
    return {
        "review_id": rid,
        "similarity_score": similarity,
        "shopee": {
            "image_url": _img(f"sp-{rid}"),
            "product_name": shopee_name,
            "product_link": f"https://shopee.ph/product/{rid}-sp",
        },
        "tiktok": {
            "image_url": _img(f"tt-{rid}"),
            "product_name": tiktok_name,
            "product_link": f"https://www.tiktok.com/view/product/{rid}-tt",
        },
    }


MOCK_ASSORTMENT_SELLERS: list[dict[str, Any]] = [
    {
        "shop_id": "100001",
        "shop_name": "NovaStyle PH",
        "shopee_link": "https://shopee.ph/novastyle.ph",
        "tiktok_shop_name": "NovaStyle Official TT",
        "mapping_status": "partial",
        "missing_count": 3,
        "need_review_count": 2,
        "price_gap_risk": True,
        "new_listings_count": 1,
        "tracker_connected": False,
        "fastmoss_connected": False,
        "data_status": "mock",
        "last_synced_at": "2026-06-06T08:00:00Z",
        "missing_products": [
            _missing("m-100001-1", "Linen Blend Summer Dress — Sage", 1299.0, 0.94),
            _missing("m-100001-2", "Crossbody Mini Bag — Copper", 899.0, 0.88),
            _missing("m-100001-3", "Platform Sandals 5cm — Black", 749.0, 0.91),
        ],
        "need_review": [
            _review(
                "r-100001-1",
                "Cotton Oversized Tee — White M",
                "Oversized Cotton T-Shirt White Medium",
                0.87,
            ),
            _review(
                "r-100001-2",
                "High-Waist Wide Pants — Navy L",
                "Wide Leg Trousers Navy Large",
                0.82,
            ),
        ],
    },
    {
        "shop_id": "100002",
        "shop_name": "UrbanPeak Retail",
        "shopee_link": "https://shopee.ph/urbanpeak.retail",
        "tiktok_shop_name": "UrbanPeak FastMoss",
        "mapping_status": "unmapped",
        "missing_count": 5,
        "need_review_count": 1,
        "price_gap_risk": True,
        "new_listings_count": 2,
        "tracker_connected": False,
        "fastmoss_connected": False,
        "data_status": "mock",
        "last_synced_at": "2026-06-06T08:00:00Z",
        "missing_products": [
            _missing("m-100002-1", "Windbreaker Jacket — Charcoal", 1899.0, 0.92),
            _missing("m-100002-2", "Cargo Jogger Pants — Olive", 1099.0, 0.85),
            _missing("m-100002-3", "Knit Beanie — Cream", 399.0, 0.79),
            _missing("m-100002-4", "Retro Runner Sneakers — Grey 42", 2199.0, 0.9),
            _missing("m-100002-5", "UV Block Cap — Navy", 549.0, 0.86),
        ],
        "need_review": [
            _review(
                "r-100002-1",
                "Fleece Hoodie Zip — Black XL",
                "Zip-Up Fleece Hoodie Black XL",
                0.91,
            ),
        ],
    },
    {
        "shop_id": "100003",
        "shop_name": "GlowMart Official",
        "shopee_link": "https://shopee.ph/glowmart.official",
        "tiktok_shop_name": "GlowMart TikTok Shop",
        "mapping_status": "mapped",
        "missing_count": 1,
        "need_review_count": 3,
        "price_gap_risk": False,
        "new_listings_count": 0,
        "tracker_connected": False,
        "fastmoss_connected": False,
        "data_status": "mock",
        "last_synced_at": "2026-06-06T08:00:00Z",
        "missing_products": [
            _missing("m-100003-1", "Vitamin C Serum 30ml — Bright", 649.0, 0.93),
        ],
        "need_review": [
            _review(
                "r-100003-1",
                "Hydrating Toner 200ml",
                "Moisture Boost Toner 200ml",
                0.89,
            ),
            _review(
                "r-100003-2",
                "SPF50 Sunscreen Gel",
                "UV Shield Gel SPF 50",
                0.84,
            ),
            _review(
                "r-100003-3",
                "Night Repair Cream 50g",
                "Overnight Recovery Cream",
                0.8,
            ),
        ],
    },
    {
        "shop_id": "100004",
        "shop_name": "TechHive Direct",
        "shopee_link": "https://shopee.ph/techhive.direct",
        "tiktok_shop_name": "TechHive FM Store",
        "mapping_status": "partial",
        "missing_count": 2,
        "need_review_count": 2,
        "price_gap_risk": True,
        "new_listings_count": 3,
        "tracker_connected": False,
        "fastmoss_connected": False,
        "data_status": "mock",
        "last_synced_at": "2026-06-06T08:00:00Z",
        "missing_products": [
            _missing("m-100004-1", "USB-C Hub 7-in-1 — Aluminum", 1599.0, 0.95),
            _missing("m-100004-2", "Wireless Earbuds Pro — Black", 2499.0, 0.9),
        ],
        "need_review": [
            _review(
                "r-100004-1",
                "65W GaN Charger Dual Port",
                "65W Fast Charger 2-Port GaN",
                0.88,
            ),
            _review(
                "r-100004-2",
                "Mechanical Keyboard RGB TKL",
                "RGB TKL Mechanical Keyboard",
                0.76,
            ),
        ],
    },
    {
        "shop_id": "100005",
        "shop_name": "HomeNest Living",
        "shopee_link": "https://shopee.ph/homenest.living",
        "tiktok_shop_name": "HomeNest Living TT",
        "mapping_status": "partial",
        "missing_count": 4,
        "need_review_count": 1,
        "price_gap_risk": False,
        "new_listings_count": 1,
        "tracker_connected": False,
        "fastmoss_connected": False,
        "data_status": "mock",
        "last_synced_at": "2026-06-06T08:00:00Z",
        "missing_products": [
            _missing("m-100005-1", "Memory Foam Pillow — Cooling", 899.0, 0.87),
            _missing("m-100005-2", "Ceramic Non-Stick Pan 28cm", 1199.0, 0.9),
            _missing("m-100005-3", "Linen Duvet Cover Set — Sand", 2299.0, 0.92),
            _missing("m-100005-4", "Desk Organizer Bamboo", 499.0, 0.81),
        ],
        "need_review": [
            _review(
                "r-100005-1",
                "Aroma Diffuser 300ml — Wood",
                "Wooden Essential Oil Diffuser 300ml",
                0.86,
            ),
        ],
    },
]


def get_mock_assortment_intelligence() -> dict[str, Any]:
    """Full assortment module payload with product-level mock data."""
    if not MOCK_ASSORTMENT_SELLERS:
        shops = [(s["shop_id"], s["shop_name"]) for s in MOCK_BUSINESS_INPUTS]
        return {
            "module": "assortment_intelligence",
            "version": "v1",
            "status": "mock",
            "sellers": [],
        }
    return {
        "module": "assortment_intelligence",
        "version": "v1",
        "status": "mock",
        "tracker_connected": False,
        "fastmoss_connected": False,
        "sellers": MOCK_ASSORTMENT_SELLERS,
    }
