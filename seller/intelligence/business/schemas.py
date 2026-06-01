"""Business Intelligence V1 — field shapes."""

from __future__ import annotations

from typing import TypedDict


class BusinessIntelligenceInput(TypedDict):
    """Raw inputs per seller (Shopee USD + TikTok PHP)."""

    shop_id: str
    shop_name: str
    shopee_mtd_adgmv_usd: float
    shopee_m1_adgmv_usd: float
    tiktok_mtd_adgmv_php: float
    tiktok_m1_adgmv_php: float


class BusinessIntelligenceRecord(TypedDict):
    """Fully calculated seller record."""

    shop_id: str
    shop_name: str
    shopee_mtd_adgmv_usd: float
    tiktok_mtd_adgmv_php: float
    tiktok_mtd_adgmv_usd: float
    shopee_m1_adgmv_usd: float
    tiktok_m1_adgmv_php: float
    tiktok_m1_adgmv_usd: float
    shopee_mom_percent: float | None
    tiktok_mom_percent: float | None
    mtd_shopee_sob_percent: float | None
    mtd_tiktok_sob_percent: float | None
    m1_shopee_sob_percent: float | None
    m1_tiktok_sob_percent: float | None
