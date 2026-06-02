"""Assortment Intelligence Phase 1 collector."""



from __future__ import annotations



import logging

import os

from datetime import UTC, datetime

from typing import Any



from seller.fastmoss.mapping import load_fastmoss_mapping
from seller.fastmoss.review import allows_tiktok_data, get_review_by_shop_id

from seller.intelligence.assortment.verification import verify_seller_assortment

from seller.intelligence.seller_master import SellerMasterRecord



logger = logging.getLogger("seller.intelligence.assortment.collector")



PHASE1_SHOP_ID = os.getenv("ASSORTMENT_PHASE1_SHOP_ID", "19100527").strip()





def _mapping_for_shop(shop_id: str) -> dict[str, Any] | None:

    payload = load_fastmoss_mapping()

    for row in payload.get("mappings") or []:

        if str(row.get("shop_id") or "").strip() == shop_id:

            return row

    return None





def analyze_shop(record: SellerMasterRecord) -> dict[str, Any]:

    """FastMoss-first Shopee verification for one seller."""

    mapping = _mapping_for_shop(record.shop_id)

    fastmoss_shop_id = str((mapping or {}).get("fastmoss_shop_id") or "").strip()

    mapping_status = str((mapping or {}).get("mapping_status") or "NOT_FOUND").lower()

    review = get_review_by_shop_id(record.shop_id)

    review_status = (review or {}).get("review_status")

    approved = allows_tiktok_data(review_status)



    if not fastmoss_shop_id or not approved:

        return {

            "shop_id": record.shop_id,

            "shop_name": record.shop_name,

            "shopee_link": record.shopee_link,

            "tiktok_shop_name": record.tiktok_shop_name,

            "mapping_status": mapping_status if mapping else "unmapped",

            "fastmoss_shop_id": None,

            "fastmoss_shop_url": (mapping or {}).get("fastmoss_shop_url"),

            "strategy": "fastmoss_first_search_verify",

            "tracker_connected": False,

            "fastmoss_connected": False,

            "data_status": "error",

            "last_synced_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),

            "catalog_stats": {

                "fastmoss_products_checked": 0,

                "fastmoss_total_cnt": None,

                "shopee_search_method": None,

                "matched_count": 0,

                "missing_count": 0,

                "need_review_count": 0,

            },

            "catalog_errors": [
                "FastMoss shop is not mapped."
                if not fastmoss_shop_id
                else "FastMoss mapping pending approval."
            ],

            "search_errors": [],

            "missing_count": 0,

            "need_review_count": 0,

            "matched_count": 0,

            "price_gap_risk": False,

            "new_listings_count": 0,

            "missing_products": [],

            "need_review": [],

            "matched_products": [],

        }



    result = verify_seller_assortment(record, fastmoss_shop_id=fastmoss_shop_id)



    return {

        "shop_id": record.shop_id,

        "shop_name": record.shop_name,

        "shopee_link": record.shopee_link,

        "tiktok_shop_name": record.tiktok_shop_name,

        "mapping_status": mapping_status if mapping else "unmapped",

        "fastmoss_shop_id": fastmoss_shop_id,

        "fastmoss_shop_url": (mapping or {}).get("fastmoss_shop_url"),

        "strategy": result.get("strategy"),

        "tracker_connected": False,

        "fastmoss_connected": result.get("fastmoss_products_checked", 0) > 0,

        "data_status": result.get("data_status"),

        "last_synced_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),

        "catalog_stats": {

            "fastmoss_products_checked": result.get("fastmoss_products_checked", 0),

            "fastmoss_total_cnt": result.get("fastmoss_total_cnt"),

            "shopee_search_method": result.get("shopee_search_method"),

            "matched_count": result.get("matched_count", 0),

            "missing_count": result.get("missing_count", 0),

            "need_review_count": result.get("need_review_count", 0),

        },

        "catalog_errors": result.get("catalog_errors") or [],

        "search_errors": result.get("search_errors") or [],

        "missing_count": result.get("missing_count", 0),

        "need_review_count": result.get("need_review_count", 0),

        "matched_count": result.get("matched_count", 0),

        "price_gap_risk": False,

        "new_listings_count": 0,

        "missing_products": result.get("missing_products") or [],

        "need_review": result.get("need_review") or [],

        "matched_products": result.get("matched_products") or [],

        "verification_results": result.get("verification_results") or [],

    }





def is_phase1_shop(shop_id: str) -> bool:

    return str(shop_id or "").strip() == PHASE1_SHOP_ID

