"""Seller Intelligence V1 — HTTP API (mock / structure / placeholder)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends

from seller.auth.dependencies import require_auth
from seller.intelligence import get_seller_intelligence_v1_snapshot
from seller.intelligence.assortment import get_mock_assortment_intelligence
from seller.intelligence.business.meta import get_mock_business_intelligence_payload
from seller.intelligence.config import USD_PHP_RATE
from seller.intelligence.periods import resolve_periods
from seller.intelligence.voucher import build_voucher_intelligence_placeholder

router = APIRouter(
    prefix="/api/intelligence/v1",
    tags=["seller-intelligence-v1"],
    dependencies=[Depends(require_auth)],
)


def _shop_list() -> list[tuple[str, str]]:
    business = get_mock_business_intelligence_payload()
    return [(r["shop_id"], r["shop_name"]) for r in business]


@router.get("")
async def intelligence_v1_snapshot():
    """Full V1 snapshot: business, assortment structure, voucher placeholder."""
    return get_seller_intelligence_v1_snapshot()


@router.get("/dashboard")
async def intelligence_v1_dashboard():
    """V1 dashboard summary (periods + module status)."""
    today = date.today()
    business = get_mock_business_intelligence_payload()
    return {
        "version": "v1",
        "reference_today": today.isoformat(),
        "periods": resolve_periods(today).as_dict(),
        "usd_php_rate": USD_PHP_RATE,
        "seller_count": len(business),
        "modules": {
            "business_intelligence": {
                "status": "mock_data",
                "seller_count": len(business),
            },
            "assortment_intelligence": {
                "status": "mock",
                "tracker_connected": False,
                "fastmoss_connected": False,
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
    return {
        "version": "v1",
        "data_source": "mock",
        "periods": resolve_periods(today).as_dict(),
        "usd_php_rate": USD_PHP_RATE,
        "sellers": get_mock_business_intelligence_payload(),
    }


@router.get("/assortment")
async def intelligence_v1_assortment():
    return get_mock_assortment_intelligence()


@router.get("/voucher")
async def intelligence_v1_voucher():
    return build_voucher_intelligence_placeholder(_shop_list())
