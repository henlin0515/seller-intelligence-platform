"""Business Intelligence V1 — seller master + FastMoss TikTok data."""

from __future__ import annotations

from typing import Any

from seller.fastmoss.mapping import load_fastmoss_mapping
from seller.intelligence.business.calculations import mom_percent, tiktok_php_to_usd
from seller.intelligence.business.store import (
    fastmoss_collection_by_shop_id,
    load_business_intelligence_data,
)
from seller.intelligence.seller_master import SellerMasterLoadResult, get_seller_master

SHOPEE_NA_REASON = "Shopee ADGMV source not connected"
SOB_NA_REASON = "SOB requires Shopee ADGMV (not connected)"


def _mapping_by_shop_id() -> dict[str, dict[str, Any]]:
    try:
        payload = load_fastmoss_mapping()
    except OSError:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in payload.get("mappings") or []:
        if not isinstance(row, dict):
            continue
        shop_id = str(row.get("shop_id") or "").strip()
        if shop_id:
            out[shop_id] = row
    return out


def _tiktok_na_reason(
    mapping_status: str | None,
    collection_row: dict[str, Any] | None,
) -> str:
    if mapping_status != "MAPPED":
        return "FastMoss shop not mapped"
    if collection_row is None:
        return "TikTok data not collected"
    if collection_row.get("status") != "success":
        return str(collection_row.get("error") or "FastMoss collection failed")
    return "TikTok data unavailable"


def build_business_seller_record(
    *,
    shop_id: str,
    shop_name: str,
    tiktok_shop_name: str,
    mapping_row: dict[str, Any] | None,
    collection_row: dict[str, Any] | None,
) -> dict[str, Any]:
    mapping_status = str((mapping_row or {}).get("mapping_status") or "NOT_FOUND")
    fastmoss_matched_shop = (mapping_row or {}).get("fastmoss_shop_name")

    record: dict[str, Any] = {
        "shop_id": shop_id,
        "shop_name": shop_name,
        "tiktok_shop_name": tiktok_shop_name,
        "fastmoss_match_status": mapping_status,
        "fastmoss_matched_shop": fastmoss_matched_shop,
        "tiktok_mtd_gmv_php": None,
        "tiktok_m1_gmv_php": None,
        "tiktok_mtd_adgmv_php": None,
        "tiktok_m1_adgmv_php": None,
        "tiktok_mtd_adgmv_usd": None,
        "tiktok_m1_adgmv_usd": None,
        "tiktok_mom_percent": None,
        "tiktok_data_status": "na",
        "tiktok_na_reason": None,
        "shopee_mtd_adgmv_usd": None,
        "shopee_m1_adgmv_usd": None,
        "shopee_mom_percent": None,
        "shopee_na_reason": SHOPEE_NA_REASON,
        "mtd_shopee_sob_percent": None,
        "mtd_tiktok_sob_percent": None,
        "m1_shopee_sob_percent": None,
        "m1_tiktok_sob_percent": None,
        "sob_na_reason": SOB_NA_REASON,
    }

    if collection_row and collection_row.get("status") == "success":
        mtd_gmv = float(collection_row.get("mtd_gmv_php") or 0)
        m1_gmv = float(collection_row.get("m1_gmv_php") or 0)
        mtd_adgmv_php = float(collection_row.get("tiktok_mtd_adgmv_php") or 0)
        m1_adgmv_php = float(collection_row.get("tiktok_m1_adgmv_php") or 0)
        mtd_adgmv_usd = tiktok_php_to_usd(mtd_adgmv_php)
        m1_adgmv_usd = tiktok_php_to_usd(m1_adgmv_php)
        record.update(
            {
                "tiktok_mtd_gmv_php": round(mtd_gmv, 2),
                "tiktok_m1_gmv_php": round(m1_gmv, 2),
                "tiktok_mtd_adgmv_php": round(mtd_adgmv_php, 4),
                "tiktok_m1_adgmv_php": round(m1_adgmv_php, 4),
                "tiktok_mtd_adgmv_usd": round(mtd_adgmv_usd, 4),
                "tiktok_m1_adgmv_usd": round(m1_adgmv_usd, 4),
                "tiktok_mom_percent": (
                    round(mom, 4)
                    if (mom := mom_percent(mtd_adgmv_usd, m1_adgmv_usd)) is not None
                    else None
                ),
                "tiktok_data_status": "available",
                "tiktok_na_reason": None,
            }
        )
        return record

    record["tiktok_na_reason"] = _tiktok_na_reason(mapping_status, collection_row)
    return record


def get_business_intelligence_payload(
    master: SellerMasterLoadResult | None = None,
) -> list[dict[str, Any]]:
    """Return BI seller rows with real TikTok FastMoss data where collected."""
    loaded = master or get_seller_master()
    saved = load_business_intelligence_data()
    collection_by_shop = fastmoss_collection_by_shop_id(saved)
    mapping_by_shop = _mapping_by_shop_id()

    return [
        build_business_seller_record(
            shop_id=seller.shop_id,
            shop_name=seller.shop_name,
            tiktok_shop_name=seller.tiktok_shop_name,
            mapping_row=mapping_by_shop.get(seller.shop_id),
            collection_row=collection_by_shop.get(seller.shop_id),
        )
        for seller in loaded.sellers
    ]


def get_business_intelligence_meta() -> dict[str, Any]:
    saved = load_business_intelligence_data()
    if not saved:
        return {
            "fastmoss_connected": False,
            "data_file": None,
            "generated_at": None,
            "summary": None,
        }
    return {
        "fastmoss_connected": True,
        "data_file": "business_intelligence_data.json",
        "generated_at": saved.get("generated_at"),
        "reference_today": saved.get("reference_today"),
        "summary": saved.get("summary"),
        "source": saved.get("source"),
    }
