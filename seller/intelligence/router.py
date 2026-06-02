"""Seller Intelligence V1 — HTTP API (seller master from Google Sheet)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from seller.auth.dependencies import require_auth
from seller.google_sheets.exceptions import (
    GoogleSheetsNotConfiguredError,
    GoogleSheetsNotEnabledError,
)
from seller.intelligence import get_seller_intelligence_v1_snapshot
from seller.intelligence.assortment import get_assortment_intelligence
from seller.intelligence.business.meta import (
    get_business_intelligence_meta,
    get_business_intelligence_payload,
    get_shopee_adgmv_match_summary,
)
from seller.intelligence.config import USD_PHP_RATE
from seller.intelligence.periods import resolve_periods
from seller.intelligence.seller_master import get_seller_master
from seller.intelligence.voucher import build_voucher_intelligence_placeholder

router = APIRouter(
    prefix="/api/intelligence/v1",
    tags=["seller-intelligence-v1"],
    dependencies=[Depends(require_auth)],
)


def _load_master():
    try:
        return get_seller_master()
    except (GoogleSheetsNotConfiguredError, GoogleSheetsNotEnabledError) as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


def _shop_list() -> list[tuple[str, str]]:
    master = _load_master()
    return [(s.shop_id, s.shop_name) for s in master.sellers]


@router.get("")
async def intelligence_v1_snapshot():
    """Full V1 snapshot: business, assortment structure, voucher placeholder."""
    _load_master()
    return get_seller_intelligence_v1_snapshot()


@router.get("/dashboard")
async def intelligence_v1_dashboard():
    """V1 dashboard summary (periods + module status)."""
    today = date.today()
    master = _load_master()
    business = get_business_intelligence_payload(master)
    fastmoss_meta = get_business_intelligence_meta()
    imp = master.stats.as_dict()
    return {
        "version": "v1",
        "reference_today": today.isoformat(),
        "periods": resolve_periods(today).as_dict(),
        "usd_php_rate": USD_PHP_RATE,
        "data_source": master.data_source,
        "tab": master.tab,
        "seller_count": len(business),
        "import": imp,
        "modules": {
            "business_intelligence": {
                "status": "fastmoss_tiktok" if fastmoss_meta.get("fastmoss_connected") else "sheet_master",
                "seller_count": len(business),
                "fastmoss_connected": fastmoss_meta.get("fastmoss_connected", False),
                "tiktok_collected": (fastmoss_meta.get("summary") or {}).get("success"),
            },
            "assortment_intelligence": {
                "status": "sheet_master",
                "tracker_connected": False,
                "fastmoss_connected": fastmoss_meta.get("fastmoss_connected", False),
            },
            "voucher_intelligence": {
                "status": "placeholder",
                "value": "N/A",
            },
        },
    }


@router.get("/business")
async def intelligence_v1_business():
    today = date.today()
    master = _load_master()
    fastmoss_meta = get_business_intelligence_meta()
    sellers = get_business_intelligence_payload(master)
    tiktok_available = sum(1 for s in sellers if s.get("tiktok_data_status") == "available")
    shopee_available = sum(1 for s in sellers if s.get("shopee_data_status") == "available")
    return {
        "version": "v1",
        "data_source": master.data_source,
        "tab": master.tab,
        "periods": resolve_periods(today).as_dict(),
        "usd_php_rate": USD_PHP_RATE,
        "fastmoss": fastmoss_meta,
        "summary": {
            "seller_count": len(sellers),
            "tiktok_available": tiktok_available,
            "tiktok_na": len(sellers) - tiktok_available,
            "shopee_available": shopee_available,
            "shopee_na": len(sellers) - shopee_available,
        },
        "sellers": sellers,
        "shopee_adgmv": get_shopee_adgmv_match_summary(master),
        "import": master.stats.as_dict(),
    }


@router.get("/assortment")
async def intelligence_v1_assortment():
    master = _load_master()
    return get_assortment_intelligence(master)


@router.get("/voucher")
async def intelligence_v1_voucher():
    return build_voucher_intelligence_placeholder(_shop_list())
