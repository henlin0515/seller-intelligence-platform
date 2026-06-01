"""Assortment Intelligence V1 — structure only (no real data yet)."""

from __future__ import annotations

from typing import TypedDict


class AssortmentIntelligenceSeller(TypedDict):
    """Per-seller assortment intelligence shell — data sources not connected."""

    shop_id: str
    shop_name: str
    data_status: str  # e.g. "structure_only"
    tracker_connected: bool
    fastmoss_connected: bool
    missing_assortment_count: None
    need_review_count: None
    price_gap_alert_count: None
    new_listing_alert_count: None
    last_synced_at: None


class AssortmentIntelligenceModule(TypedDict):
    module: str
    version: str
    status: str
    sellers: list[AssortmentIntelligenceSeller]


def build_assortment_intelligence_structure(
    shop_ids: list[tuple[str, str]],
) -> AssortmentIntelligenceModule:
    """Build placeholder structure for sellers (no Tracker / FastMoss)."""
    return AssortmentIntelligenceModule(
        module="assortment_intelligence",
        version="v1",
        status="structure_only",
        sellers=[
            AssortmentIntelligenceSeller(
                shop_id=shop_id,
                shop_name=shop_name,
                data_status="no_data",
                tracker_connected=False,
                fastmoss_connected=False,
                missing_assortment_count=None,
                need_review_count=None,
                price_gap_alert_count=None,
                new_listing_alert_count=None,
                last_synced_at=None,
            )
            for shop_id, shop_name in shop_ids
        ],
    )
