"""Unified intelligence data refresh — sheets, mapping, review, approved TikTok BI."""

from __future__ import annotations

import time
from datetime import date
from typing import Any

from seller.fastmoss.mapping import (
    MAPPING_MAPPED,
    load_fastmoss_mapping,
    refresh_unresolved_fastmoss_mapping,
)
from seller.fastmoss.review import (
    REVIEW_APPROVED,
    approved_mapping_rows,
    list_review_rows,
    review_summary,
    sync_reviews_from_mappings,
)
from seller.intelligence.business.collector import collect_mapped_shop_tiktok
from seller.intelligence.business.store import (
    fastmoss_collection_by_shop_id,
    load_business_intelligence_data,
    save_business_intelligence_data,
)
from seller.intelligence.config import USD_PHP_RATE
from seller.intelligence.periods import resolve_periods


def refresh_tiktok_bi_for_shop_ids(
    shop_ids: list[str],
    *,
    delay_sec: float = 0.35,
) -> dict[str, Any]:
    """Collect FastMoss TikTok GMV for specific approved shop IDs."""
    wanted = {str(shop_id) for shop_id in shop_ids if str(shop_id).strip()}
    if not wanted:
        return {"approved_count": 0, "tiktok_data_refreshed_count": 0, "collection_success": 0}

    today = date.today()
    periods = resolve_periods(today)
    approved = [row for row in approved_mapping_rows() if str(row.get("shop_id")) in wanted]
    bi_data = load_business_intelligence_data() or {
        "reference_today": today.isoformat(),
        "periods": periods.as_dict(),
        "usd_php_rate": USD_PHP_RATE,
        "source": "fastmoss_recentData",
        "sellers": [],
    }
    approved_ids = {str(r.get("shop_id")) for r in approved_mapping_rows()}
    collection_by_shop = {
        sid: row
        for sid, row in fastmoss_collection_by_shop_id(bi_data).items()
        if sid in approved_ids
    }

    refreshed = 0
    updated_rows: list[dict[str, Any]] = []
    for index, row in enumerate(approved):
        shop_id = str(row.get("shop_id") or "")
        if not shop_id:
            continue
        if index > 0 and delay_sec > 0:
            time.sleep(delay_sec)
        collected = collect_mapped_shop_tiktok(row, periods, delay_sec=0)
        collection_by_shop[shop_id] = collected
        updated_rows.append(collected)
        if collected.get("status") == "success":
            refreshed += 1

    sellers_list = list(collection_by_shop.values())
    success = sum(1 for row in sellers_list if row.get("status") == "success")
    bi_data.update(
        {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "reference_today": today.isoformat(),
            "periods": periods.as_dict(),
            "usd_php_rate": USD_PHP_RATE,
            "source": "fastmoss_recentData",
            "summary": {
                "processed": len(sellers_list),
                "success": success,
                "failed": len(sellers_list) - success,
                "approved_only": True,
            },
            "sellers": sellers_list,
        }
    )
    save_business_intelligence_data(bi_data)
    return {
        "shop_ids": sorted(wanted),
        "approved_count": len(approved),
        "tiktok_data_refreshed_count": refreshed,
        "collection_success": refreshed,
        "shops": updated_rows,
    }


def refresh_approved_tiktok_bi(*, delay_sec: float = 0.35) -> dict[str, Any]:
    """Collect FastMoss TikTok GMV only for APPROVED mappings."""
    today = date.today()
    periods = resolve_periods(today)
    approved = approved_mapping_rows()
    bi_data = load_business_intelligence_data() or {
        "reference_today": today.isoformat(),
        "periods": periods.as_dict(),
        "usd_php_rate": USD_PHP_RATE,
        "source": "fastmoss_recentData",
        "sellers": [],
    }
    approved_ids = {str(r.get("shop_id")) for r in approved}
    collection_by_shop = {
        sid: row
        for sid, row in fastmoss_collection_by_shop_id(bi_data).items()
        if sid in approved_ids
    }

    refreshed = 0
    for index, row in enumerate(approved):
        shop_id = str(row.get("shop_id") or "")
        if not shop_id:
            continue
        if index > 0 and delay_sec > 0:
            time.sleep(delay_sec)
        collected = collect_mapped_shop_tiktok(row, periods, delay_sec=0)
        collection_by_shop[shop_id] = collected
        if collected.get("status") == "success":
            refreshed += 1

    sellers_list = list(collection_by_shop.values())
    success = sum(1 for row in sellers_list if row.get("status") == "success")
    bi_data.update(
        {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "reference_today": today.isoformat(),
            "periods": periods.as_dict(),
            "usd_php_rate": USD_PHP_RATE,
            "source": "fastmoss_recentData",
            "summary": {
                "processed": len(sellers_list),
                "success": success,
                "failed": len(sellers_list) - success,
                "approved_only": True,
            },
            "sellers": sellers_list,
        }
    )
    save_business_intelligence_data(bi_data)
    return {
        "approved_count": len(approved),
        "tiktok_data_refreshed_count": refreshed,
        "collection_success": success,
    }


def refresh_all_intelligence_data() -> dict[str, Any]:
    """Refresh sheets, remap FastMoss, audit reviews, and reload approved TikTok BI."""
    from seller.intelligence.assortment.radar import clear_tiktok_radar_cache
    from seller.intelligence.router import _refresh_all_sheet_caches

    sheet_result = _refresh_all_sheet_caches()
    clear_tiktok_radar_cache()
    # Re-match NOT_FOUND / NEED_REVIEW with multi-keyword search; keep MAPPED rows.
    mapping_result = refresh_unresolved_fastmoss_mapping()

    payload = load_fastmoss_mapping()
    mappings = payload.get("mappings") or []
    mapping_result["summary"] = payload.get("summary") or {}
    sync_reviews_from_mappings(mappings)
    bi_result = refresh_approved_tiktok_bi()

    from seller.intelligence.historical_sob import refresh_historical_sob
    from seller.intelligence.seller_master import get_seller_master
    from seller.intelligence.assortment.service import get_assortment_intelligence

    historical_sob_result = refresh_historical_sob(force=True)

    from seller.intelligence.assortment.radar import start_radar_fastmoss_refresh_background

    radar_refresh = start_radar_fastmoss_refresh_background(get_seller_master())

    summary = review_summary()
    pending = [r for r in list_review_rows() if r.get("review_status") == "PENDING_REVIEW"][:10]
    rejected = [r for r in list_review_rows() if r.get("review_status") == "REJECTED"][:10]

    return {
        "success": True,
        "refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sheets": sheet_result,
        "mapping": mapping_result,
        "review": summary,
        "tiktok_bi": bi_result,
        "historical_sob": historical_sob_result,
        "tiktok_product_radar": radar_refresh,
        "pending_preview": pending,
        "rejected_preview": rejected,
    }
