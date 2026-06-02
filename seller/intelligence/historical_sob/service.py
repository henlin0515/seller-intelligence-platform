"""Historical SOB Analysis — join seller master, YTD sheet, approved TikTok mappings."""

from __future__ import annotations

import logging
import time
from typing import Any

from seller.fastmoss.mapping import MAPPING_MAPPED, load_fastmoss_mapping
from seller.fastmoss.review import REVIEW_APPROVED, allows_tiktok_data, get_review_by_shop_id
from seller.intelligence.business.calculations import sob_pair
from seller.intelligence.historical_sob.collector import fetch_shop_historical_tiktok_gmv
from seller.intelligence.historical_sob.portfolio import (
    build_portfolio_historical_sob,
    build_tiktok_threat_sellers,
    build_top_sob_movers,
)
from seller.intelligence.historical_sob.store import (
    load_historical_sob_cache,
    save_historical_sob_cache,
    shop_tiktok_cache_row,
)
from seller.intelligence.historical_sob.ytd_monthly import get_ytd_monthly
from seller.intelligence.seller_master import SellerMasterLoadResult, get_seller_master

logger = logging.getLogger("seller.intelligence.historical_sob.service")


def _round_gmv(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def _round_sob(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 1)


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


def _review_status_for_shop(shop_id: str) -> str:
    review = get_review_by_shop_id(shop_id)
    if review and review.get("review_status"):
        return str(review["review_status"])
    mapping = _mapping_by_shop_id().get(str(shop_id)) or {}
    status = str(mapping.get("mapping_status") or "NOT_FOUND").upper()
    if status != MAPPING_MAPPED:
        return "NOT_MAPPED"
    return "PENDING_REVIEW"


def _shop_sob_row(
    *,
    shop_id: str,
    shop_name: str,
    tiktok_shop_name: str,
    mapping_row: dict[str, Any] | None,
    review_status: str,
    ytd_row: Any | None,
    tiktok_cache: dict[str, Any] | None,
) -> dict[str, Any]:
    april_shopee = _round_gmv(ytd_row.april_shopee_gmv) if ytd_row else None
    may_shopee = _round_gmv(ytd_row.may_shopee_gmv) if ytd_row else None

    april_tiktok = None
    may_tiktok = None
    tiktok_status = "na"
    tiktok_na_reason = None

    if allows_tiktok_data(review_status) and mapping_row:
        fastmoss_id = str(mapping_row.get("fastmoss_shop_id") or "").strip()
        if fastmoss_id and tiktok_cache and tiktok_cache.get("status") == "success":
            april_tiktok = _round_gmv(tiktok_cache.get("april_gmv_php"))
            may_tiktok = _round_gmv(tiktok_cache.get("may_gmv_php"))
            tiktok_status = "available"
        elif not fastmoss_id:
            tiktok_na_reason = "FastMoss shop not mapped"
        elif tiktok_cache and tiktok_cache.get("status") != "success":
            tiktok_na_reason = str(tiktok_cache.get("error") or "TikTok historical fetch failed")
        else:
            tiktok_na_reason = "TikTok historical data not cached"
    elif review_status != REVIEW_APPROVED:
        tiktok_na_reason = f"Mapping status: {review_status}"
    else:
        tiktok_na_reason = "FastMoss shop not mapped"

    april_total = (
        (april_shopee + april_tiktok)
        if april_shopee is not None and april_tiktok is not None
        else None
    )
    may_total = (
        (may_shopee + may_tiktok) if may_shopee is not None and may_tiktok is not None else None
    )

    april_shopee_sob, april_tiktok_sob = (
        sob_pair(float(april_shopee), float(april_tiktok))
        if april_shopee is not None and april_tiktok is not None
        else (None, None)
    )
    may_shopee_sob, may_tiktok_sob = (
        sob_pair(float(may_shopee), float(may_tiktok))
        if may_shopee is not None and may_tiktok is not None
        else (None, None)
    )

    sob_change_pp = None
    if april_tiktok_sob is not None and may_tiktok_sob is not None:
        sob_change_pp = _round_sob(float(may_tiktok_sob) - float(april_tiktok_sob))

    category = None
    if mapping_row:
        category = mapping_row.get("category") or mapping_row.get("fastmoss_category")

    return {
        "shop_id": shop_id,
        "shop_name": shop_name,
        "tiktok_shop_name": tiktok_shop_name,
        "mapping_status": review_status,
        "tiktok_mapping_status": review_status,
        "category": category,
        "fastmoss_shop_id": (mapping_row or {}).get("fastmoss_shop_id"),
        "fastmoss_shop_name": (mapping_row or {}).get("fastmoss_shop_name"),
        "april_shopee_gmv": april_shopee,
        "april_tiktok_gmv": april_tiktok,
        "april_total_gmv": _round_gmv(april_total),
        "may_shopee_gmv": may_shopee,
        "may_tiktok_gmv": may_tiktok,
        "may_total_gmv": _round_gmv(may_total),
        "april_shopee_sob_percent": _round_sob(april_shopee_sob),
        "april_tiktok_sob_percent": _round_sob(april_tiktok_sob),
        "may_shopee_sob_percent": _round_sob(may_shopee_sob),
        "may_tiktok_sob_percent": _round_sob(may_tiktok_sob),
        "sob_change_pp": sob_change_pp,
        "shopee_data_status": "available" if ytd_row else "na",
        "tiktok_data_status": tiktok_status,
        "tiktok_na_reason": tiktok_na_reason,
    }


def build_historical_sob_rows(
    master: SellerMasterLoadResult,
    *,
    tiktok_cache: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    ytd = get_ytd_monthly()
    mappings = _mapping_by_shop_id()
    cache = tiktok_cache if tiktok_cache is not None else load_historical_sob_cache()
    rows: list[dict[str, Any]] = []

    for seller in master.sellers:
        shop_id = str(seller.shop_id)
        mapping_row = mappings.get(shop_id)
        review_status = _review_status_for_shop(shop_id)
        ytd_row = ytd.by_shop_id.get(shop_id)
        tiktok_row = shop_tiktok_cache_row(cache, shop_id)
        rows.append(
            _shop_sob_row(
                shop_id=shop_id,
                shop_name=seller.shop_name,
                tiktok_shop_name=seller.tiktok_shop_name,
                mapping_row=mapping_row,
                review_status=review_status,
                ytd_row=ytd_row,
                tiktok_cache=tiktok_row,
            )
        )

    rows.sort(key=lambda r: str(r.get("shop_name") or "").lower())
    return rows


def _summary_counts(rows: list[dict[str, Any]], master: SellerMasterLoadResult) -> dict[str, Any]:
    ytd = get_ytd_monthly()
    cache = load_historical_sob_cache()
    cached_shops = cache.get("shops") or {}
    tiktok_success = sum(
        1 for row in cached_shops.values() if isinstance(row, dict) and row.get("status") == "success"
    )
    april_sob = sum(1 for r in rows if r.get("april_shopee_sob_percent") is not None)
    may_sob = sum(1 for r in rows if r.get("may_shopee_sob_percent") is not None)
    return {
        "master_seller_count": len(master.sellers),
        "ytd_monthly_rows_loaded": ytd.stats.total_loaded,
        "tiktok_historical_fetched_count": tiktok_success,
        "april_sob_calculated_count": april_sob,
        "may_sob_calculated_count": may_sob,
    }


def refresh_historical_sob_tiktok_cache(
    master: SellerMasterLoadResult | None = None,
    *,
    delay_sec: float = 0.35,
    force: bool = False,
) -> dict[str, Any]:
    """Fetch April/May TikTok GMV for approved mappings; persist cache file."""
    from seller.fastmoss.review import approved_mapping_rows

    master = master or get_seller_master()
    master_ids = {str(s.shop_id) for s in master.sellers}
    approved = [row for row in approved_mapping_rows() if str(row.get("shop_id")) in master_ids]

    cache = load_historical_sob_cache()
    shops: dict[str, Any] = dict(cache.get("shops") or {})
    fetched = 0
    failed = 0
    skipped = 0

    for index, row in enumerate(approved):
        shop_id = str(row.get("shop_id") or "")
        fastmoss_id = str(row.get("fastmoss_shop_id") or "").strip()
        if not shop_id or not fastmoss_id:
            skipped += 1
            continue

        existing = shops.get(shop_id)
        if (
            not force
            and isinstance(existing, dict)
            and existing.get("status") == "success"
            and existing.get("fastmoss_shop_id") == fastmoss_id
            and existing.get("april_gmv_php") is not None
            and existing.get("may_gmv_php") is not None
        ):
            continue

        if index > 0 and delay_sec > 0:
            time.sleep(delay_sec)

        try:
            collected = fetch_shop_historical_tiktok_gmv(fastmoss_id, delay_sec=0)
            collected["shop_id"] = shop_id
            collected["tiktok_shop_name"] = row.get("tiktok_shop_name")
            shops[shop_id] = collected
            fetched += 1
        except Exception as exc:
            logger.warning("Historical TikTok fetch failed for shop %s: %s", shop_id, exc)
            shops[shop_id] = {
                "shop_id": shop_id,
                "fastmoss_shop_id": fastmoss_id,
                "status": "failed",
                "error": str(exc),
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            failed += 1

    cache["shops"] = shops
    save_historical_sob_cache(cache)
    return {
        "approved_count": len(approved),
        "fetched_count": fetched,
        "failed_count": failed,
        "skipped_cached_count": len(approved) - fetched - failed - skipped,
        "cache_shop_count": len(shops),
    }


def refresh_historical_sob(*, force: bool = True) -> dict[str, Any]:
    """Reload sheets and refresh TikTok historical cache."""
    master = get_seller_master(force_refresh=True)
    get_ytd_monthly(force_refresh=True)
    tiktok_result = refresh_historical_sob_tiktok_cache(master, force=force)
    rows = build_historical_sob_rows(master)
    return {
        "success": True,
        "refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": _summary_counts(rows, master),
        "tiktok_cache": tiktok_result,
    }


def get_historical_sob_payload(
    master: SellerMasterLoadResult | None = None,
    *,
    ensure_tiktok_cache: bool = True,
) -> dict[str, Any]:
    master = master or get_seller_master()
    ytd = get_ytd_monthly()
    cache = load_historical_sob_cache()

    if ensure_tiktok_cache and not cache.get("shops"):
        refresh_historical_sob_tiktok_cache(master, force=False)

    rows = build_historical_sob_rows(master)
    portfolio = build_portfolio_historical_sob(rows)
    summary = _summary_counts(rows, master)
    categories = sorted(
        {str(r.get("category")).strip() for r in rows if r.get("category")},
        key=str.lower,
    )

    return {
        "version": "v1",
        "module": "historical_sob",
        "master_tab": master.tab,
        "ytd_tab": ytd.tab,
        "periods": {
            "april": {"start": "2026-04-01", "end": "2026-04-30", "shopee_multiplier": 30},
            "may": {"start": "2026-05-01", "end": "2026-05-31", "shopee_multiplier": 31},
        },
        "cache_updated_at": cache.get("updated_at"),
        "summary": summary,
        "kpis": {
            "total_shops": len(master.sellers),
            "april_shopee_gmv": portfolio.get("april_shopee_gmv"),
            "april_tiktok_gmv": portfolio.get("april_tiktok_gmv"),
            "may_shopee_gmv": portfolio.get("may_shopee_gmv"),
            "may_tiktok_gmv": portfolio.get("may_tiktok_gmv"),
            "april_portfolio_shopee_sob_percent": portfolio.get("april_shopee_sob_percent"),
            "april_portfolio_tiktok_sob_percent": portfolio.get("april_tiktok_sob_percent"),
            "may_portfolio_shopee_sob_percent": portfolio.get("may_shopee_sob_percent"),
            "may_portfolio_tiktok_sob_percent": portfolio.get("may_tiktok_sob_percent"),
        },
        "portfolio": portfolio,
        "top_sob_movers": build_top_sob_movers(rows),
        "tiktok_threat_sellers": build_tiktok_threat_sellers(rows),
        "sellers": rows,
        "filters": {
            "mapping_statuses": sorted({str(r.get("mapping_status")) for r in rows}),
            "categories": categories,
            "months": ["all", "april", "may"],
        },
    }
