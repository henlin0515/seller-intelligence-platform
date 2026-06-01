"""Business Intelligence V1 — currency, MoM, and SOB calculations."""

from __future__ import annotations

from seller.intelligence.business.schemas import (
    BusinessIntelligenceInput,
    BusinessIntelligenceRecord,
)
from seller.intelligence.config import USD_PHP_RATE


def tiktok_php_to_usd(php: float) -> float:
    """tiktok_usd = tiktok_php / USD_PHP_RATE"""
    return php / USD_PHP_RATE


def mom_percent(mtd_usd: float, m1_usd: float) -> float | None:
    """(mtd - m1) / m1 * 100. Returns None when M-1 is zero."""
    if m1_usd == 0:
        return None
    return (mtd_usd - m1_usd) / m1_usd * 100.0


def sob_pair(
    shopee_usd: float, tiktok_usd: float
) -> tuple[float | None, float | None]:
    """
    Shopee SOB and TikTok SOB for a period. Pair totals 100% when total > 0.
    """
    total = shopee_usd + tiktok_usd
    if total == 0:
        return None, None
    shopee_sob = shopee_usd / total * 100.0
    tiktok_sob = tiktok_usd / total * 100.0
    return shopee_sob, tiktok_sob


def _round_pct(value: float | None, places: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, places)


def build_business_intelligence_record(
    raw: BusinessIntelligenceInput,
) -> BusinessIntelligenceRecord:
    """Apply V1 formulas to raw Shopee USD + TikTok PHP inputs."""
    tiktok_mtd_usd = tiktok_php_to_usd(raw["tiktok_mtd_adgmv_php"])
    tiktok_m1_usd = tiktok_php_to_usd(raw["tiktok_m1_adgmv_php"])

    shopee_mom = mom_percent(raw["shopee_mtd_adgmv_usd"], raw["shopee_m1_adgmv_usd"])
    tiktok_mom = mom_percent(tiktok_mtd_usd, tiktok_m1_usd)

    mtd_shopee_sob, mtd_tiktok_sob = sob_pair(
        raw["shopee_mtd_adgmv_usd"], tiktok_mtd_usd
    )
    m1_shopee_sob, m1_tiktok_sob = sob_pair(
        raw["shopee_m1_adgmv_usd"], tiktok_m1_usd
    )

    return BusinessIntelligenceRecord(
        shop_id=raw["shop_id"],
        shop_name=raw["shop_name"],
        shopee_mtd_adgmv_usd=raw["shopee_mtd_adgmv_usd"],
        tiktok_mtd_adgmv_php=raw["tiktok_mtd_adgmv_php"],
        tiktok_mtd_adgmv_usd=tiktok_mtd_usd,
        shopee_m1_adgmv_usd=raw["shopee_m1_adgmv_usd"],
        tiktok_m1_adgmv_php=raw["tiktok_m1_adgmv_php"],
        tiktok_m1_adgmv_usd=tiktok_m1_usd,
        shopee_mom_percent=_round_pct(shopee_mom),
        tiktok_mom_percent=_round_pct(tiktok_mom),
        mtd_shopee_sob_percent=_round_pct(mtd_shopee_sob),
        mtd_tiktok_sob_percent=_round_pct(mtd_tiktok_sob),
        m1_shopee_sob_percent=_round_pct(m1_shopee_sob),
        m1_tiktok_sob_percent=_round_pct(m1_tiktok_sob),
    )


def build_all_business_intelligence(
    sellers: list[BusinessIntelligenceInput],
) -> list[BusinessIntelligenceRecord]:
    return [build_business_intelligence_record(s) for s in sellers]
