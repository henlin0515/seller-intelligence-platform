"""Historical SOB Analysis — join seller master, YTD sheet, approved TikTok mappings."""

from __future__ import annotations

import logging
import time
import traceback
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
from seller.intelligence.historical_sob.ytd_monthly import YtdMonthlyLoadResult, get_ytd_monthly
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
    try:
        review = get_review_by_shop_id(shop_id)
        if review and review.get("review_status"):
            return str(review["review_status"])
    except Exception as exc:
        logger.warning("Review lookup failed for shop %s: %s", shop_id, exc)
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
    shopee_na_reason = None
    if ytd_row is None:
        shopee_na_reason = "No ytd monthly data row for shop_id"
    elif ytd_row.ytd_ap_adgmv is None and ytd_row.ytd_may_adgmv is None:
        shopee_na_reason = "Missing ytd_ap_adgmv and ytd_may_adgmv"
    elif ytd_row.ytd_ap_adgmv is None:
        shopee_na_reason = "Missing ytd_ap_adgmv"
    elif ytd_row.ytd_may_adgmv is None:
        shopee_na_reason = "Missing ytd_may_adgmv"

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
            if april_tiktok is None and may_tiktok is None:
                tiktok_na_reason = "FastMoss sale_amount missing for April and May"
            elif april_tiktok is None:
                tiktok_na_reason = "FastMoss sale_amount missing for April"
            elif may_tiktok is None:
                tiktok_na_reason = "FastMoss sale_amount missing for May"
            else:
                tiktok_status = "available"
        elif not fastmoss_id:
            tiktok_na_reason = "FastMoss shop not mapped"
        elif tiktok_cache and tiktok_cache.get("status") != "success":
            tiktok_na_reason = str(tiktok_cache.get("error") or "TikTok historical fetch failed")
        else:
            tiktok_na_reason = "TikTok historical data not cached — click Refresh Data"
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
        "shopee_data_status": "available" if april_shopee is not None or may_shopee is not None else "na",
        "shopee_na_reason": shopee_na_reason,
        "tiktok_data_status": tiktok_status,
        "tiktok_na_reason": tiktok_na_reason,
    }


def build_historical_sob_rows(
    master: SellerMasterLoadResult,
    *,
    ytd: YtdMonthlyLoadResult | None = None,
    tiktok_cache: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    ytd = ytd or get_ytd_monthly()
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


def _tiktok_cache_counts(cache: dict[str, Any]) -> dict[str, int]:
    shops = cache.get("shops") or {}
    april = 0
    may = 0
    success = 0
    for row in shops.values():
        if not isinstance(row, dict) or row.get("status") != "success":
            continue
        success += 1
        if row.get("april_gmv_php") is not None:
            april += 1
        if row.get("may_gmv_php") is not None:
            may += 1
    return {
        "tiktok_historical_fetched_count": success,
        "tiktok_april_gmv_fetched_count": april,
        "tiktok_may_gmv_fetched_count": may,
    }


def _summary_counts(
    rows: list[dict[str, Any]],
    master: SellerMasterLoadResult,
    *,
    ytd: YtdMonthlyLoadResult,
    cache: dict[str, Any],
) -> dict[str, Any]:
    tiktok_counts = _tiktok_cache_counts(cache)
    april_sob = sum(1 for r in rows if r.get("april_shopee_sob_percent") is not None)
    may_sob = sum(1 for r in rows if r.get("may_shopee_sob_percent") is not None)
    return {
        "master_seller_count": len(master.sellers),
        "ytd_monthly_rows_loaded": ytd.stats.total_loaded,
        "ytd_load_error": ytd.load_error,
        **tiktok_counts,
        "april_sob_calculated_count": april_sob,
        "may_sob_calculated_count": may_sob,
    }


def _na_preview(rows: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for row in rows:
        reasons: list[str] = []
        if row.get("shopee_na_reason"):
            reasons.append(str(row["shopee_na_reason"]))
        if row.get("tiktok_na_reason") and row.get("tiktok_data_status") != "available":
            reasons.append(str(row["tiktok_na_reason"]))
        if not reasons:
            continue
        preview.append(
            {
                "shop_id": row.get("shop_id"),
                "shop_name": row.get("shop_name"),
                "reasons": reasons,
            }
        )
        if len(preview) >= limit:
            break
    return preview


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
    counts = _tiktok_cache_counts(cache)
    return {
        "approved_count": len(approved),
        "fetched_count": fetched,
        "failed_count": failed,
        "skipped_cached_count": max(0, len(approved) - fetched - failed - skipped),
        "cache_shop_count": len(shops),
        **counts,
    }


def refresh_historical_sob(*, force: bool = True) -> dict[str, Any]:
    """Reload sheets and refresh TikTok historical cache."""
    master = get_seller_master(force_refresh=True)
    ytd = get_ytd_monthly(force_refresh=True)
    tiktok_result = refresh_historical_sob_tiktok_cache(master, force=force)
    cache = load_historical_sob_cache()
    rows = build_historical_sob_rows(master, ytd=ytd, tiktok_cache=cache)
    return {
        "success": True,
        "refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": _summary_counts(rows, master, ytd=ytd, cache=cache),
        "tiktok_cache": tiktok_result,
    }


def _build_payload(
    master: SellerMasterLoadResult,
    *,
    ytd: YtdMonthlyLoadResult,
    cache: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    rows = build_historical_sob_rows(master, ytd=ytd, tiktok_cache=cache)
    portfolio = build_portfolio_historical_sob(rows)
    summary = _summary_counts(rows, master, ytd=ytd, cache=cache)
    categories = sorted(
        {str(r.get("category")).strip() for r in rows if r.get("category")},
        key=str.lower,
    )

    return {
        "version": "v1",
        "module": "historical_sob",
        "status": "ok",
        "master_tab": master.tab,
        "ytd_tab": ytd.tab,
        "periods": {
            "april": {"start": "2026-04-01", "end": "2026-04-30", "shopee_multiplier": 30},
            "may": {"start": "2026-05-01", "end": "2026-05-31", "shopee_multiplier": 31},
        },
        "cache_updated_at": cache.get("updated_at"),
        "warnings": warnings,
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
        "na_preview": _na_preview(rows),
        "filters": {
            "mapping_statuses": sorted({str(r.get("mapping_status")) for r in rows}),
            "categories": categories,
            "months": ["all", "april", "may"],
        },
    }


def _empty_payload(*, master: SellerMasterLoadResult | None, error: str) -> dict[str, Any]:
    return {
        "version": "v1",
        "module": "historical_sob",
        "status": "degraded",
        "master_tab": getattr(master, "tab", "shpoee link"),
        "ytd_tab": get_ytd_monthly().tab,
        "warnings": [error],
        "summary": {
            "master_seller_count": len(master.sellers) if master else 0,
            "ytd_monthly_rows_loaded": 0,
            "tiktok_historical_fetched_count": 0,
            "tiktok_april_gmv_fetched_count": 0,
            "tiktok_may_gmv_fetched_count": 0,
            "april_sob_calculated_count": 0,
            "may_sob_calculated_count": 0,
        },
        "kpis": {
            "total_shops": len(master.sellers) if master else 0,
            "april_shopee_gmv": None,
            "april_tiktok_gmv": None,
            "may_shopee_gmv": None,
            "may_tiktok_gmv": None,
            "april_portfolio_shopee_sob_percent": None,
            "april_portfolio_tiktok_sob_percent": None,
            "may_portfolio_shopee_sob_percent": None,
            "may_portfolio_tiktok_sob_percent": None,
        },
        "portfolio": {},
        "top_sob_movers": [],
        "tiktok_threat_sellers": [],
        "sellers": [],
        "na_preview": [],
        "filters": {"mapping_statuses": [], "categories": [], "months": ["all", "april", "may"]},
    }


def get_historical_sob_payload(
    master: SellerMasterLoadResult | None = None,
    *,
    ensure_tiktok_cache: bool = False,
) -> dict[str, Any]:
    """Build Historical SOB payload; never raises HTTP-facing errors."""
    warnings: list[str] = []
    try:
        master = master or get_seller_master()
        ytd = get_ytd_monthly()
        cache = load_historical_sob_cache()

        if ytd.load_error:
            warnings.append(ytd.load_error)
        if not ytd.by_shop_id:
            warnings.append(
                "No rows loaded from ytd monthly data — Shopee GMV will show N/A until the tab is available."
            )
        if ensure_tiktok_cache and not cache.get("shops"):
            try:
                refresh_historical_sob_tiktok_cache(master, force=False)
                cache = load_historical_sob_cache()
            except Exception as exc:
                logger.exception("Historical SOB TikTok cache bootstrap failed")
                warnings.append(f"TikTok historical cache refresh failed: {exc}")
        elif not cache.get("shops"):
            warnings.append(
                "TikTok April/May GMV not cached yet — click Refresh Data to fetch FastMoss historical GMV."
            )

        return _build_payload(master, ytd=ytd, cache=cache, warnings=warnings)
    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("Historical SOB payload failed:\n%s", tb)
        message = f"Historical SOB load error: {exc}"
        try:
            master = master or get_seller_master()
        except Exception:
            master = None
        payload = _empty_payload(master=master, error=message)
        return payload
