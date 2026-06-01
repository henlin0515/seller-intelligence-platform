"""
Seller Intelligence V1 — three modules:

1. Business Intelligence (formulas + mock data)
2. Assortment Intelligence (structure only)
3. Voucher Intelligence (placeholder N/A)
"""

from __future__ import annotations

from datetime import date

from seller.intelligence.assortment import get_mock_assortment_intelligence
from seller.intelligence.business.meta import get_mock_business_intelligence_payload
from seller.intelligence.config import USD_PHP_RATE
from seller.intelligence.periods import resolve_periods
from seller.intelligence.voucher import build_voucher_intelligence_placeholder


def get_seller_intelligence_v1_snapshot(
    reference_today: date | None = None,
) -> dict[str, object]:
    """In-memory V1 snapshot: business (calculated mock), assortment structure, voucher N/A."""
    today = reference_today or date.today()
    business = get_mock_business_intelligence_payload()
    shops = [(r["shop_id"], r["shop_name"]) for r in business]
    return {
        "version": "v1",
        "reference_today": today.isoformat(),
        "periods": resolve_periods(today).as_dict(),
        "usd_php_rate": USD_PHP_RATE,
        "business_intelligence": business,
        "assortment_intelligence": get_mock_assortment_intelligence(),
        "voucher_intelligence": build_voucher_intelligence_placeholder(shops),
    }


__all__ = [
    "USD_PHP_RATE",
    "build_voucher_intelligence_placeholder",
    "get_mock_assortment_intelligence",
    "get_mock_business_intelligence_payload",
    "get_seller_intelligence_v1_snapshot",
    "resolve_periods",
]
