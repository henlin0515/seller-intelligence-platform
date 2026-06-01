"""Voucher Intelligence V1 — placeholder only."""

from __future__ import annotations

from typing import Any, TypedDict

NA = "N/A"


class VoucherIntelligenceSeller(TypedDict):
    shop_id: str
    shop_name: str
    active_voucher_count: str
    competitor_voucher_status: str
    last_checked_at: str
    data_source: str


class VoucherIntelligenceModule(TypedDict):
    module: str
    version: str
    status: str
    sellers: list[VoucherIntelligenceSeller]


def build_voucher_intelligence_placeholder(
    shop_ids: list[tuple[str, str]],
) -> VoucherIntelligenceModule:
    """All voucher fields show N/A — no scraping or tracker connection."""
    return VoucherIntelligenceModule(
        module="voucher_intelligence",
        version="v1",
        status="placeholder",
        sellers=[
            VoucherIntelligenceSeller(
                shop_id=shop_id,
                shop_name=shop_name,
                active_voucher_count=NA,
                competitor_voucher_status=NA,
                last_checked_at=NA,
                data_source=NA,
            )
            for shop_id, shop_name in shop_ids
        ],
    )


def voucher_field_value() -> str:
    return NA


def voucher_payload_summary() -> dict[str, Any]:
    return {
        "module": "voucher_intelligence",
        "version": "v1",
        "status": "placeholder",
        "value": NA,
    }
