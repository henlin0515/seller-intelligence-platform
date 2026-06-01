"""Business Intelligence V1 — mock inputs for 5 sellers (calculated fields via formulas)."""

from __future__ import annotations

from seller.intelligence.business.calculations import build_all_business_intelligence
from seller.intelligence.business.schemas import (
    BusinessIntelligenceInput,
    BusinessIntelligenceRecord,
)

# Shopee = USD. TikTok = PHP (converted in calculations).
MOCK_BUSINESS_INPUTS: list[BusinessIntelligenceInput] = [
    {
        "shop_id": "100001",
        "shop_name": "NovaStyle PH",
        "shopee_mtd_adgmv_usd": 185_000.0,
        "shopee_m1_adgmv_usd": 172_000.0,
        "tiktok_mtd_adgmv_php": 4_632_000.0,
        "tiktok_m1_adgmv_php": 4_100_000.0,
    },
    {
        "shop_id": "100002",
        "shop_name": "UrbanPeak Retail",
        "shopee_mtd_adgmv_usd": 92_500.0,
        "shopee_m1_adgmv_usd": 98_000.0,
        "tiktok_mtd_adgmv_php": 2_157_250.0,
        "tiktok_m1_adgmv_php": 2_340_000.0,
    },
    {
        "shop_id": "100003",
        "shop_name": "GlowMart Official",
        "shopee_mtd_adgmv_usd": 310_400.0,
        "shopee_m1_adgmv_usd": 305_000.0,
        "tiktok_mtd_adgmv_php": 6_155_000.0,
        "tiktok_m1_adgmv_php": 5_900_000.0,
    },
    {
        "shop_id": "100004",
        "shop_name": "TechHive Direct",
        "shopee_mtd_adgmv_usd": 64_200.0,
        "shopee_m1_adgmv_usd": 70_500.0,
        "tiktok_mtd_adgmv_php": 1_231_000.0,
        "tiktok_m1_adgmv_php": 1_480_000.0,
    },
    {
        "shop_id": "100005",
        "shop_name": "HomeNest Living",
        "shopee_mtd_adgmv_usd": 128_750.0,
        "shopee_m1_adgmv_usd": 120_000.0,
        "tiktok_mtd_adgmv_php": 3_077_500.0,
        "tiktok_m1_adgmv_php": 2_950_000.0,
    },
]


def get_mock_business_intelligence() -> list[BusinessIntelligenceRecord]:
    """Return 5 sellers with all MoM / SOB fields calculated."""
    return build_all_business_intelligence(MOCK_BUSINESS_INPUTS)
