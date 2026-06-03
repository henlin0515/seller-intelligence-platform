"""Seller Intelligence V1 — HTTP API (seller master from Google Sheet)."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

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
from seller.intelligence.business.portfolio import build_portfolio_overview
from seller.intelligence.config import USD_PHP_RATE
from seller.intelligence.periods import resolve_periods
from seller.intelligence.seller_master import (
    clear_seller_master_cache,
    get_seller_master,
    get_seller_master_sync_status,
)
from seller.intelligence.voucher import build_voucher_intelligence_placeholder

logger = logging.getLogger("seller.intelligence.router")

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
    portfolio = build_portfolio_overview(business, total_sellers=len(business))
    return {
        "version": "v1",
        "reference_today": today.isoformat(),
        "periods": resolve_periods(today).as_dict(),
        "usd_php_rate": USD_PHP_RATE,
        "data_source": master.data_source,
        "tab": master.tab,
        "seller_count": len(business),
        "portfolio": portfolio,
        "import": imp,
        "modules": {
            "business_intelligence": {
                "status": "fastmoss_tiktok" if fastmoss_meta.get("fastmoss_connected") else "sheet_master",
                "seller_count": len(business),
                "fastmoss_connected": fastmoss_meta.get("fastmoss_connected", False),
                "tiktok_collected": (fastmoss_meta.get("summary") or {}).get("success"),
            },
            "assortment_intelligence": {
                "status": "tiktok_product_radar",
                "tracker_connected": False,
                "fastmoss_connected": fastmoss_meta.get("fastmoss_connected", False),
            },
            "voucher_intelligence": {
                "status": "placeholder",
                "value": "N/A",
            },
        },
    }


@router.post("/business/refresh-data")
async def intelligence_v1_business_refresh_data():
    """Start Seller Level Analysis Update Data (background, progress via refresh-status)."""
    from seller.intelligence.business.sla_refresh import start_sla_refresh_background

    return await asyncio.to_thread(start_sla_refresh_background)


@router.get("/business/refresh-status")
async def intelligence_v1_business_refresh_status():
    """Poll Seller Level Analysis Update Data progress."""
    from seller.intelligence.business.sla_refresh import get_sla_refresh_status

    return get_sla_refresh_status()


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
async def intelligence_v1_assortment(refresh: bool = False):
    """Fast sheet-aligned payload by default; FastMoss catalog only when refresh=true."""
    import asyncio

    master = _load_master()
    try:
        return await asyncio.to_thread(
            get_assortment_intelligence,
            master,
            force_refresh=refresh,
            fetch_fastmoss=refresh,
        )
    except Exception as exc:
        logger.exception("TikTok Product Radar load failed")
        raise HTTPException(
            status_code=500,
            detail="Could not load TikTok Product Radar.",
        ) from exc


@router.post("/assortment/refresh-products")
async def intelligence_v1_assortment_refresh_products():
    """Kick off background FastMoss product catalog refresh (non-blocking)."""
    import asyncio

    from seller.intelligence.assortment.radar import start_radar_fastmoss_refresh_background

    master = _load_master()
    return await asyncio.to_thread(start_radar_fastmoss_refresh_background, master)


@router.get("/voucher")
async def intelligence_v1_voucher():
    return build_voucher_intelligence_placeholder(_shop_list())


@router.get("/historical-sob")
async def intelligence_v1_historical_sob():
    """Historical April/May SOB — seller master + YTD sheet + cached FastMoss TikTok GMV."""
    import asyncio

    from seller.intelligence.historical_sob import get_historical_sob_payload

    try:
        master = _load_master()
        payload = await asyncio.to_thread(get_historical_sob_payload, master, ensure_tiktok_cache=True)
        if payload.get("status") == "degraded":
            logger.error("Historical SOB degraded response: %s", payload.get("warnings"))
        return payload
    except (GoogleSheetsNotConfiguredError, GoogleSheetsNotEnabledError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Historical SOB endpoint failure")
        from seller.intelligence.historical_sob.service import _empty_payload

        return _empty_payload(master=None, error=str(exc))


@router.get("/seller-master/status")
async def intelligence_v1_seller_master_status():
    """Seller Master cache sync metadata for Settings."""
    try:
        status = get_seller_master_sync_status()
        if not status.get("last_sync_at"):
            _load_master()
            status = get_seller_master_sync_status()
        return {"version": "v1", **status}
    except (GoogleSheetsNotConfiguredError, GoogleSheetsNotEnabledError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _refresh_all_sheet_caches() -> dict:
    """Clear and reload Seller Master, AI data, Shopee ADGMV, and radar caches."""
    from seller.intelligence.assortment.radar import clear_tiktok_radar_cache
    from seller.intelligence.business.shopee_adgmv import clear_shopee_adgmv_cache, get_shopee_adgmv
    from seller.sheets_cache import refresh as refresh_ai_data

    clear_seller_master_cache()
    clear_shopee_adgmv_cache()
    clear_tiktok_radar_cache()
    from seller.intelligence.historical_sob.ytd_monthly import clear_ytd_monthly_cache

    clear_ytd_monthly_cache()

    master = get_seller_master(force_refresh=True)
    ai_status = refresh_ai_data(force=True)
    adgmv = get_shopee_adgmv(force_refresh=True)

    from seller.intelligence.assortment.radar import start_radar_fastmoss_refresh_background

    radar_refresh = start_radar_fastmoss_refresh_background(master)

    sync_status = get_seller_master_sync_status()
    refreshed_at = sync_status.get("last_sync_at") or datetime.now(timezone.utc).isoformat()

    return {
        "success": True,
        "refreshed_at": refreshed_at,
        "seller_count": len(master.sellers),
        "ai_data_count": int(ai_status.get("seller_count") or 0),
        "shopee_adgmv_count": adgmv.stats.total_loaded,
        "tiktok_product_radar": {
            "refresh_started": radar_refresh.get("started"),
            "refresh_running": radar_refresh.get("running"),
        },
    }


@router.post("/refresh-data")
async def intelligence_v1_refresh_data():
    """Refresh sheets, FastMoss mapping, review audit, approved TikTok BI, and Shopee ADGMV."""
    from seller.intelligence.refresh_data import refresh_all_intelligence_data

    try:
        return await asyncio.to_thread(refresh_all_intelligence_data)
    except (GoogleSheetsNotConfiguredError, GoogleSheetsNotEnabledError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Intelligence data refresh failed")
        raise HTTPException(
            status_code=500,
            detail="Could not refresh intelligence data. Try again later.",
        ) from exc


@router.post("/refresh-sheets")
async def intelligence_v1_refresh_sheets():
    """Legacy alias — runs full intelligence refresh pipeline."""
    return await intelligence_v1_refresh_data()


@router.post("/refresh-fastmoss-mapping")
async def intelligence_v1_refresh_fastmoss_mapping(force_all: bool = False):
    """Legacy alias — runs full intelligence refresh pipeline."""
    _ = force_all
    return await intelligence_v1_refresh_data()


@router.post("/refresh-fastmoss-mapping-not-found")
async def intelligence_v1_refresh_fastmoss_not_found():
    """Re-run enhanced FastMoss search for NOT_FOUND + NEED_REVIEW (MAPPED rows unchanged)."""
    from seller.fastmoss.mapping import refresh_unresolved_fastmoss_mapping

    return await asyncio.to_thread(refresh_unresolved_fastmoss_mapping)


@router.get("/mapping-review")
async def intelligence_v1_mapping_review_list():
    """List FastMoss mapping review rows and summary counts."""
    from seller.fastmoss.review import ensure_review_store_synced, list_review_rows, review_summary

    ensure_review_store_synced()
    rows = list_review_rows()
    summary = review_summary()
    pending = [r for r in rows if r.get("review_status") == "PENDING_REVIEW"][:10]
    rejected = [r for r in rows if r.get("review_status") == "REJECTED"][:10]
    return {
        "summary": summary,
        "rows": rows,
        "pending_preview": pending,
        "rejected_preview": rejected,
    }


@router.get("/mapping-review/{shop_id}/search")
async def intelligence_v1_mapping_review_search(shop_id: str):
    """Search FastMoss for alternative shop matches."""
    from seller.fastmoss.mapping import load_fastmoss_mapping
    from seller.fastmoss.search import search_shop_candidates

    payload = load_fastmoss_mapping()
    mapping_row = None
    for row in payload.get("mappings") or []:
        if str(row.get("shop_id")) == str(shop_id):
            mapping_row = row
            break
    if mapping_row is None:
        raise HTTPException(status_code=404, detail=f"Shop {shop_id} not found")

    tiktok_name = str(mapping_row.get("tiktok_shop_name") or "").strip()
    if not tiktok_name:
        raise HTTPException(status_code=400, detail="TikTok shop name is empty")

    candidates = await asyncio.to_thread(
        search_shop_candidates,
        tiktok_name,
        tiktok_shop_name=tiktok_name,
        page_size=5,
    )
    return {
        "shop_id": shop_id,
        "tiktok_shop_name": tiktok_name,
        "candidates": candidates,
    }


@router.post("/mapping-review/{shop_id}/approve")
async def intelligence_v1_mapping_review_approve(
    shop_id: str,
    username: str = Depends(require_auth),
    notes: str | None = None,
):
    from seller.fastmoss.review import REVIEW_APPROVED, set_review_decision

    try:
        record = await asyncio.to_thread(
            set_review_decision,
            shop_id,
            review_status=REVIEW_APPROVED,
            reviewed_by=username,
            notes=notes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "review": record}


@router.post("/mapping-review/{shop_id}/reject")
async def intelligence_v1_mapping_review_reject(
    shop_id: str,
    username: str = Depends(require_auth),
    notes: str | None = None,
):
    from seller.fastmoss.review import REVIEW_REJECTED, set_review_decision

    try:
        record = await asyncio.to_thread(
            set_review_decision,
            shop_id,
            review_status=REVIEW_REJECTED,
            reviewed_by=username,
            notes=notes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "review": record}


@router.post("/mapping-review/{shop_id}/select")
async def intelligence_v1_mapping_review_select(
    shop_id: str,
    username: str = Depends(require_auth),
    fastmoss_shop_id: str = "",
    fastmoss_shop_name: str = "",
    fastmoss_shop_url: str | None = None,
    confidence: float | None = None,
    notes: str | None = None,
):
    from seller.fastmoss.review import REVIEW_APPROVED, set_review_decision

    if not fastmoss_shop_id or not fastmoss_shop_name:
        raise HTTPException(status_code=400, detail="fastmoss_shop_id and fastmoss_shop_name required")
    try:
        record = await asyncio.to_thread(
            set_review_decision,
            shop_id,
            review_status=REVIEW_APPROVED,
            reviewed_by=username,
            notes=notes or "Manual candidate selection",
            fastmoss_shop_id=fastmoss_shop_id,
            fastmoss_shop_name=fastmoss_shop_name,
            fastmoss_shop_url=fastmoss_shop_url,
            confidence=confidence,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "review": record}
