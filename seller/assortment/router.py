from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from seller.assortment.api_schemas import (
    CompetitorCatalogImportRequest,
    ImportResponse,
    OurCatalogImportRequest,
)
from seller.assortment.import_service import import_competitor_products, import_our_products
from seller.assortment.matching import run_matching_for_all_competitors
from seller.assortment.service import (
    confirm_match,
    dismiss_new_listing,
    get_dashboard_metrics,
    list_missing_assortment,
    list_need_review,
    list_new_listing_alerts,
    list_price_gap_analysis,
)
from seller.assortment.tracker_sync import get_tracker_payload, sync_tracker_catalog

router = APIRouter(prefix="/api/assortment", tags=["assortment"])


@router.get("/dashboard")
async def assortment_dashboard():
    return await asyncio.to_thread(get_dashboard_metrics)


@router.get("/tracker")
async def assortment_tracker():
    """COMPETITOR_TRACKER sellers + last catalog fetch status (NA when inaccessible)."""
    return await asyncio.to_thread(get_tracker_payload)


@router.post("/sync-tracker")
async def assortment_sync_tracker():
    try:
        return await asyncio.to_thread(sync_tracker_catalog, run_matching=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Tracker sync failed.") from exc


@router.get("/missing")
async def assortment_missing():
    return await asyncio.to_thread(list_missing_assortment)


@router.get("/need-review")
async def assortment_need_review():
    return await asyncio.to_thread(list_need_review)


@router.get("/price-gap")
async def assortment_price_gap():
    return await asyncio.to_thread(list_price_gap_analysis)


@router.get("/new-listings")
async def assortment_new_listings():
    return await asyncio.to_thread(list_new_listing_alerts)


@router.post("/import/our-products", response_model=ImportResponse)
async def assortment_import_our(body: OurCatalogImportRequest):
    try:
        result = await asyncio.to_thread(
            import_our_products,
            [p.model_dump() for p in body.products],
            label=body.label,
        )
        return ImportResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Import failed.") from exc


@router.post("/import/competitor-products", response_model=ImportResponse)
async def assortment_import_competitor(body: CompetitorCatalogImportRequest):
    try:
        result = await asyncio.to_thread(
            import_competitor_products,
            [p.model_dump() for p in body.products],
            label=body.label,
            competitor_shop_id=body.competitor_shop_id,
            competitor_shop_name=body.competitor_shop_name,
        )
        matching = None
        if body.run_matching:
            matching = await asyncio.to_thread(run_matching_for_all_competitors)
        return ImportResponse(**result, matching=matching)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Import failed.") from exc


@router.post("/run-matching")
async def assortment_run_matching():
    try:
        stats = await asyncio.to_thread(run_matching_for_all_competitors)
        return {"ok": True, **stats}
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Matching failed.") from exc


@router.post("/matches/{match_id}/confirm")
async def assortment_confirm_match(match_id: int):
    result = await asyncio.to_thread(confirm_match, match_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail="Match not found")
    return result


@router.post("/new-listings/{competitor_product_id}/dismiss")
async def assortment_dismiss_new_listing(competitor_product_id: int):
    result = await asyncio.to_thread(dismiss_new_listing, competitor_product_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail="Product not found")
    return result
