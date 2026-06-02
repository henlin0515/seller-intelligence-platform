"""
Seller Intelligence V1 — three modules:

1. Business Intelligence (seller master from Google Sheet)
2. Assortment Intelligence (same seller master)
3. Voucher Intelligence (placeholder N/A)
"""

from __future__ import annotations

from datetime import date

from seller.intelligence.assortment import get_assortment_intelligence
from seller.intelligence.assortment.mock_data import get_mock_assortment_intelligence
from seller.intelligence.business.meta import get_business_intelligence_payload
from seller.intelligence.config import USD_PHP_RATE
from seller.intelligence.periods import resolve_periods
from seller.intelligence.seller_master import get_seller_master
from seller.intelligence.voucher import build_voucher_intelligence_placeholder


def get_seller_intelligence_v1_snapshot(
    reference_today: date | None = None,
) -> dict[str, object]:
    """V1 snapshot: seller master (sheet), assortment shell, voucher placeholder."""
    today = reference_today or date.today()
    master = get_seller_master()
    business = get_business_intelligence_payload(master)
    shops = [(r["shop_id"], r["shop_name"]) for r in business]
    return {
        "version": "v1",
        "reference_today": today.isoformat(),
        "periods": resolve_periods(today).as_dict(),
        "usd_php_rate": USD_PHP_RATE,
        "data_source": master.data_source,
        "import": master.stats.as_dict(),
        "business_intelligence": business,
        "assortment_intelligence": get_assortment_intelligence(master),
        "voucher_intelligence": build_voucher_intelligence_placeholder(shops),
    }


__all__ = [
    "USD_PHP_RATE",
    "build_voucher_intelligence_placeholder",
    "get_assortment_intelligence",
    "get_business_intelligence_payload",
    "get_mock_assortment_intelligence",
    "get_seller_intelligence_v1_snapshot",
    "get_seller_master",
    "resolve_periods",
]
