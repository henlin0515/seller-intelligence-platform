"""Historical SOB Analysis — join seller master, YTD sheet, approved TikTok mappings."""

from __future__ import annotations

import logging
import time
import traceback
from typing import Any

from seller.fastmoss.mapping import (
    MAPPING_MAPPED,
    MAPPING_NEED_REVIEW,
    MAPPING_NOT_FOUND,
    load_fastmoss_mapping,
)
from seller.fastmoss.review import REVIEW_APPROVED, allows_tiktok_data, get_review_by_shop_id
from seller.intelligence.gp_shop_rm import normalize_shop_key
from seller.intelligence.business.calculations import sob_pair, tiktok_php_to_usd
from seller.intelligence.config import USD_PHP_RATE
from seller.intelligence.historical_sob.collector import fetch_shop_historical_tiktok_gmv
from seller.intelligence.historical_sob.portfolio import build_portfolio_historical_sob
from seller.intelligence.historical_sob.store import (
    HISTORICAL_PERIODS,
    load_historical_sob_cache,
    resolve_tiktok_cache_row,
    save_historical_sob_cache,
)
from seller.intelligence.platform_extra_shops import PlatformSource, try_load_platform_extra_shops
from seller.intelligence.historical_sob.ytd_monthly import (
    YtdMonthlyLoadResult,
    get_ytd_monthly,
    lookup_ytd_record,
)
from seller.intelligence.seller_master import SellerMasterLoadResult, get_seller_master

logger = logging.getLogger("seller.intelligence.historical_sob.service")


def _round_gmv(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def _tiktok_gmv_usd(php: float | None) -> float | None:
    """FastMoss historical GMV is PHP; convert to USD before totals and SOB."""
    if php is None:
        return None
    return _round_gmv(tiktok_php_to_usd(float(php)))


def _round_sob(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 1)


_STATUS_RANK = {MAPPING_MAPPED: 3, MAPPING_NEED_REVIEW: 2, MAPPING_NOT_FOUND: 1}


def _mapping_status_rank(status: str | None) -> int:
    return _STATUS_RANK.get(str(status or "").upper(), 0)


def _fastmoss_mapping_indexes() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Same fastmoss_mapping.json as Seller Level Analysis — by shop_id and shop name key."""
    try:
        payload = load_fastmoss_mapping()
    except OSError:
        return {}, {}
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for row in payload.get("mappings") or []:
        if not isinstance(row, dict):
            continue
        shop_id = str(row.get("shop_id") or "").strip()
        if shop_id:
            by_id[shop_id] = row
        for raw_name in (row.get("shop_name"), row.get("tiktok_shop_name")):
            key = normalize_shop_key(str(raw_name or ""))
            if not key:
                continue
            prev = by_name.get(key)
            if prev is None or _mapping_status_rank(row.get("mapping_status")) > _mapping_status_rank(
                prev.get("mapping_status")
            ):
                by_name[key] = row
    return by_id, by_name


def resolve_fastmoss_mapping_row(
    shop_id: str,
    shop_name: str,
    *,
    tiktok_shop_name: str = "",
    by_id: dict[str, dict[str, Any]] | None = None,
    by_name: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if by_id is None or by_name is None:
        by_id, by_name = _fastmoss_mapping_indexes()
    sid = str(shop_id or "").strip()
    if sid and sid in by_id:
        return by_id[sid]
    for raw in (shop_name, tiktok_shop_name):
        key = normalize_shop_key(str(raw or ""))
        if key and key in by_name:
            return by_name[key]
    return None


def _category_by_shop_key(category_mapping: dict[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for cat in (category_mapping or {}).get("categories") or []:
        if not isinstance(cat, dict):
            continue
        name = str(cat.get("name") or "").strip()
        if not name:
            continue
        for key in cat.get("shop_keys") or []:
            sk = str(key or "").strip()
            if sk:
                out[sk] = name
    return out


def _shop_category(
    *,
    shop_name: str,
    tiktok_shop_name: str,
    category_by_key: dict[str, str],
) -> str:
    for raw in (shop_name, tiktok_shop_name):
        key = normalize_shop_key(str(raw or ""))
        if key and key in category_by_key:
            return category_by_key[key]
    return "Uncategorized"


def _historical_period_sob(
    shopee_usd: float | None,
    tiktok_usd: float | None,
    *,
    platform_source: PlatformSource,
) -> tuple[float | None, float | None]:
    if platform_source == "SHOPEE_ONLY":
        if shopee_usd is None or shopee_usd <= 0:
            return None, None
        return 100.0, 0.0
    if platform_source == "TIKTOK_ONLY":
        if tiktok_usd is None or tiktok_usd <= 0:
            return None, None
        return 0.0, 100.0
    if shopee_usd is None or tiktok_usd is None:
        return None, None
    return sob_pair(float(shopee_usd), float(tiktok_usd))


def _shop_sob_row(
    *,
    shop_id: str,
    shop_name: str,
    tiktok_shop_name: str,
    mapping_row: dict[str, Any] | None,
    review_status: str,
    fastmoss_match_status: str,
    category: str,
    platform_source: PlatformSource,
    gp_shop_id: str | None = None,
    gp_shop_name: str | None = None,
    rm: str | None = None,
    ytd_row: Any | None,
    tiktok_cache: dict[str, Any] | None,
) -> dict[str, Any]:
    shopee_na_reason = None
    if ytd_row is None:
        shopee_na_reason = "No ytd monthly data row matched by shop_id"
    elif ytd_row.ytd_may_adgmv is None and ytd_row.ytd_june_adgmv is None:
        shopee_na_reason = "Missing ytd_may_adgmv and ytd_june_adgmv"
    elif ytd_row.ytd_may_adgmv is None:
        shopee_na_reason = "Missing ytd_may_adgmv"
    elif ytd_row.ytd_june_adgmv is None:
        shopee_na_reason = "Missing ytd_june_adgmv"

    may_shopee = _round_gmv(ytd_row.may_shopee_gmv) if ytd_row else None
    june_shopee = _round_gmv(ytd_row.june_shopee_gmv) if ytd_row else None

    may_tiktok = None
    june_tiktok = None
    tiktok_status = "na"
    tiktok_na_reason = None

    if platform_source == "SHOPEE_ONLY":
        tiktok_na_reason = "Shopee-only shop — no TikTok historical GMV"
    elif platform_source == "TIKTOK_ONLY":
        shopee_na_reason = "TikTok-only shop — no Shopee historical GMV"
        if mapping_row and tiktok_cache and tiktok_cache.get("status") == "success":
            may_tiktok = _tiktok_gmv_usd(tiktok_cache.get("may_gmv_php"))
            june_tiktok = _tiktok_gmv_usd(tiktok_cache.get("june_gmv_php"))
            if may_tiktok is not None or june_tiktok is not None:
                tiktok_status = "available"
                tiktok_na_reason = None
        elif mapping_row:
            tiktok_na_reason = str(tiktok_cache.get("error") if tiktok_cache else "TikTok historical data not cached")
        else:
            tiktok_na_reason = "FastMoss shop not mapped"
    elif mapping_row and (
        allows_tiktok_data(review_status)
        or str(fastmoss_match_status or "").upper() == MAPPING_MAPPED
    ):
        fastmoss_id = str(mapping_row.get("fastmoss_shop_id") or "").strip()
        if fastmoss_id and tiktok_cache and tiktok_cache.get("status") == "success":
            may_tiktok = _tiktok_gmv_usd(tiktok_cache.get("may_gmv_php"))
            june_tiktok = _tiktok_gmv_usd(tiktok_cache.get("june_gmv_php"))
            if may_tiktok is None and june_tiktok is None:
                tiktok_na_reason = "FastMoss sale_amount missing for May and June"
            elif may_tiktok is None:
                tiktok_na_reason = "FastMoss sale_amount missing for May"
            elif june_tiktok is None:
                tiktok_na_reason = "FastMoss sale_amount missing for June"
            else:
                tiktok_status = "available"
        elif not fastmoss_id:
            tiktok_na_reason = "FastMoss shop not mapped"
        elif tiktok_cache and tiktok_cache.get("status") != "success":
            tiktok_na_reason = str(tiktok_cache.get("error") or "TikTok historical fetch failed")
        else:
            tiktok_na_reason = "TikTok historical data not cached — click Refresh Data"
    elif review_status and review_status != REVIEW_APPROVED:
        tiktok_na_reason = f"Mapping status: {review_status}"
    else:
        tiktok_na_reason = "FastMoss shop not mapped"

    may_shopee_sob, may_tiktok_sob = _historical_period_sob(
        may_shopee, may_tiktok, platform_source=platform_source
    )
    june_shopee_sob, june_tiktok_sob = _historical_period_sob(
        june_shopee, june_tiktok, platform_source=platform_source
    )

    may_total = None
    if may_shopee is not None or may_tiktok is not None:
        may_total = (may_shopee or 0) + (may_tiktok or 0)
    june_total = None
    if june_shopee is not None or june_tiktok is not None:
        june_total = (june_shopee or 0) + (june_tiktok or 0)

    sob_change_pp = None
    if may_tiktok_sob is not None and june_tiktok_sob is not None:
        sob_change_pp = _round_sob(float(june_tiktok_sob) - float(may_tiktok_sob))

    return {
        "shop_id": shop_id,
        "shop_name": shop_name,
        "tiktok_shop_name": tiktok_shop_name,
        "platform_source": platform_source,
        "gp_shop_id": gp_shop_id,
        "gp_shop_name": gp_shop_name,
        "rm": rm,
        "fastmoss_match_status": fastmoss_match_status,
        "fastmoss_review_status": review_status or None,
        "mapping_status": fastmoss_match_status,
        "tiktok_mapping_status": review_status,
        "category": category,
        "fastmoss_shop_id": (mapping_row or {}).get("fastmoss_shop_id"),
        "fastmoss_shop_name": (mapping_row or {}).get("fastmoss_shop_name"),
        "may_shopee_gmv": may_shopee,
        "may_tiktok_gmv": may_tiktok,
        "may_total_gmv": _round_gmv(may_total),
        "june_shopee_gmv": june_shopee,
        "june_tiktok_gmv": june_tiktok,
        "june_total_gmv": _round_gmv(june_total),
        "may_sob_percent": _round_sob(may_tiktok_sob),
        "june_sob_percent": _round_sob(june_tiktok_sob),
        "may_shopee_sob_percent": _round_sob(may_shopee_sob),
        "may_tiktok_sob_percent": _round_sob(may_tiktok_sob),
        "june_shopee_sob_percent": _round_sob(june_shopee_sob),
        "june_tiktok_sob_percent": _round_sob(june_tiktok_sob),
        "sob_change_pp": sob_change_pp,
        "shopee_data_status": "available" if may_shopee is not None or june_shopee is not None else "na",
        "shopee_na_reason": shopee_na_reason,
        "tiktok_data_status": tiktok_status,
        "tiktok_na_reason": tiktok_na_reason,
    }


def _merge_gp_metadata(record: dict[str, Any], *, gp_shop_id: str, gp_shop_name: str, rm: str) -> None:
    if gp_shop_id and not record.get("gp_shop_id"):
        record["gp_shop_id"] = gp_shop_id
    if gp_shop_name and not record.get("gp_shop_name"):
        record["gp_shop_name"] = gp_shop_name
    if rm and not record.get("rm"):
        record["rm"] = rm


def _seller_keys(shop_name: str, tiktok_shop_name: str) -> list[str]:
    return [k for k in (normalize_shop_key(shop_name), normalize_shop_key(tiktok_shop_name)) if k]


def _find_existing_row_id(
    *,
    shop_id: str,
    shop_name: str,
    tiktok_shop_name: str,
    by_id: dict[str, dict[str, Any]],
    by_name_key: dict[str, str],
) -> str | None:
    sid = str(shop_id or "").strip()
    if sid and sid in by_id:
        return sid
    for key in _seller_keys(shop_name, tiktok_shop_name):
        if key in by_name_key:
            return by_name_key[key]
    return None


def _append_historical_row(
    rows_by_id: dict[str, dict[str, Any]],
    by_name_key: dict[str, str],
    *,
    shop_id: str,
    shop_name: str,
    tiktok_shop_name: str,
    platform_source: PlatformSource,
    gp_shop_id: str | None,
    gp_shop_name: str | None,
    rm: str | None,
    ytd: YtdMonthlyLoadResult,
    cache: dict[str, Any],
    mapping_by_id: dict[str, dict[str, Any]],
    mapping_by_name: dict[str, dict[str, Any]],
    category_by_key: dict[str, str],
) -> None:
    mapping_row = resolve_fastmoss_mapping_row(
        shop_id,
        shop_name,
        tiktok_shop_name=tiktok_shop_name,
        by_id=mapping_by_id,
        by_name=mapping_by_name,
    )
    review_row = get_review_by_shop_id(shop_id)
    review_status = str((review_row or {}).get("review_status") or "")
    fastmoss_match_status = str(
        (mapping_row or {}).get("mapping_status") or MAPPING_NOT_FOUND
    ).upper()
    record = _shop_sob_row(
        shop_id=shop_id,
        shop_name=shop_name,
        tiktok_shop_name=tiktok_shop_name,
        mapping_row=mapping_row,
        review_status=review_status,
        fastmoss_match_status=fastmoss_match_status,
        category=_shop_category(
            shop_name=shop_name,
            tiktok_shop_name=tiktok_shop_name,
            category_by_key=category_by_key,
        ),
        platform_source=platform_source,
        gp_shop_id=gp_shop_id,
        gp_shop_name=gp_shop_name,
        rm=rm,
        ytd_row=lookup_ytd_record(ytd, shop_name=shop_name, shop_id=shop_id),
        tiktok_cache=resolve_tiktok_cache_row(
            cache, shop_id=shop_id, tiktok_shop_name=tiktok_shop_name
        ),
    )
    sid = str(record["shop_id"])
    rows_by_id[sid] = record
    for key in _seller_keys(shop_name, tiktok_shop_name):
        by_name_key[key] = sid


def build_historical_sob_rows(
    master: SellerMasterLoadResult,
    *,
    ytd: YtdMonthlyLoadResult | None = None,
    tiktok_cache: dict[str, Any] | None = None,
    category_mapping: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Union of shpoee link + shopee shop only + tiktok shop only (same merge rules as SLA)."""
    ytd = ytd or get_ytd_monthly()
    by_id_map, by_name_map = _fastmoss_mapping_indexes()
    category_by_key = _category_by_shop_key(category_mapping)
    cache = tiktok_cache if tiktok_cache is not None else load_historical_sob_cache()
    shopee_only, tiktok_only = try_load_platform_extra_shops()

    rows_by_id: dict[str, dict[str, Any]] = {}
    by_name_key: dict[str, str] = {}

    for seller in master.sellers:
        _append_historical_row(
            rows_by_id,
            by_name_key,
            shop_id=str(seller.shop_id),
            shop_name=seller.shop_name,
            tiktok_shop_name=seller.tiktok_shop_name,
            platform_source="NORMAL",
            gp_shop_id=None,
            gp_shop_name=None,
            rm=None,
            ytd=ytd,
            cache=cache,
            mapping_by_id=by_id_map,
            mapping_by_name=by_name_map,
            category_by_key=category_by_key,
        )

    for extra in shopee_only.rows:
        existing_id = _find_existing_row_id(
            shop_id=extra.shop_id,
            shop_name=extra.shop_name,
            tiktok_shop_name="",
            by_id=rows_by_id,
            by_name_key=by_name_key,
        )
        if existing_id:
            _merge_gp_metadata(
                rows_by_id[existing_id],
                gp_shop_id=extra.gp_shop_id,
                gp_shop_name=extra.gp_shop_name,
                rm=extra.rm,
            )
            continue
        _append_historical_row(
            rows_by_id,
            by_name_key,
            shop_id=extra.shop_id,
            shop_name=extra.shop_name,
            tiktok_shop_name="",
            platform_source="SHOPEE_ONLY",
            gp_shop_id=extra.gp_shop_id,
            gp_shop_name=extra.gp_shop_name,
            rm=extra.rm,
            ytd=ytd,
            cache=cache,
            mapping_by_id=by_id_map,
            mapping_by_name=by_name_map,
            category_by_key=category_by_key,
        )

    for extra in tiktok_only.rows:
        sid = extra.synthetic_shop_id
        existing_id = _find_existing_row_id(
            shop_id=sid,
            shop_name="",
            tiktok_shop_name=extra.tiktok_shop_name,
            by_id=rows_by_id,
            by_name_key=by_name_key,
        )
        if existing_id:
            rec = rows_by_id[existing_id]
            _merge_gp_metadata(
                rec,
                gp_shop_id=extra.gp_shop_id,
                gp_shop_name=extra.gp_shop_name,
                rm="",
            )
            if rec.get("platform_source") == "SHOPEE_ONLY" and not rec.get("tiktok_shop_name"):
                rec["tiktok_shop_name"] = extra.tiktok_shop_name
                refreshed = _shop_sob_row(
                    shop_id=rec["shop_id"],
                    shop_name=rec.get("shop_name", ""),
                    tiktok_shop_name=extra.tiktok_shop_name,
                    mapping_row=resolve_fastmoss_mapping_row(
                        rec["shop_id"],
                        rec.get("shop_name", ""),
                        tiktok_shop_name=extra.tiktok_shop_name,
                        by_id=by_id_map,
                        by_name=by_name_map,
                    ),
                    review_status=str(rec.get("fastmoss_review_status") or ""),
                    fastmoss_match_status=str(rec.get("fastmoss_match_status") or MAPPING_NOT_FOUND),
                    category=rec.get("category", "Uncategorized"),
                    platform_source="NORMAL",
                    gp_shop_id=rec.get("gp_shop_id"),
                    gp_shop_name=rec.get("gp_shop_name"),
                    rm=rec.get("rm"),
                    ytd_row=lookup_ytd_record(
                        ytd, shop_name=rec.get("shop_name", ""), shop_id=str(rec["shop_id"])
                    ),
                    tiktok_cache=resolve_tiktok_cache_row(
                        cache,
                        shop_id=str(rec["shop_id"]),
                        tiktok_shop_name=extra.tiktok_shop_name,
                    ),
                )
                rows_by_id[str(rec["shop_id"])] = refreshed
            continue

        _append_historical_row(
            rows_by_id,
            by_name_key,
            shop_id=sid,
            shop_name=extra.gp_shop_name or extra.tiktok_shop_name,
            tiktok_shop_name=extra.tiktok_shop_name,
            platform_source="TIKTOK_ONLY",
            gp_shop_id=extra.gp_shop_id,
            gp_shop_name=extra.gp_shop_name,
            rm=None,
            ytd=ytd,
            cache=cache,
            mapping_by_id=by_id_map,
            mapping_by_name=by_name_map,
            category_by_key=category_by_key,
        )

    rows = list(rows_by_id.values())
    rows.sort(key=lambda r: str(r.get("shop_name") or "").lower())
    return rows


def _tiktok_cache_counts(cache: dict[str, Any]) -> dict[str, int]:
    shops = cache.get("shops") or {}
    may = 0
    june = 0
    success = 0
    for row in shops.values():
        if not isinstance(row, dict) or row.get("status") != "success":
            continue
        success += 1
        if row.get("may_gmv_php") is not None:
            may += 1
        if row.get("june_gmv_php") is not None:
            june += 1
    return {
        "tiktok_historical_fetched_count": success,
        "tiktok_may_gmv_fetched_count": may,
        "tiktok_june_gmv_fetched_count": june,
    }


def _count_ytd_matched(master: SellerMasterLoadResult, ytd: YtdMonthlyLoadResult) -> int:
    matched = 0
    for seller in master.sellers:
        if lookup_ytd_record(ytd, shop_name=seller.shop_name, shop_id=str(seller.shop_id)):
            matched += 1
    return matched


def _count_ytd_unmatched(master: SellerMasterLoadResult, ytd: YtdMonthlyLoadResult) -> int:
    return len(master.sellers) - _count_ytd_matched(master, ytd)


def _summary_counts(
    rows: list[dict[str, Any]],
    master: SellerMasterLoadResult,
    *,
    ytd: YtdMonthlyLoadResult,
    cache: dict[str, Any],
    portfolio: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tiktok_counts = _tiktok_cache_counts(cache)
    portfolio = portfolio or build_portfolio_historical_sob(rows)
    may_sob = sum(1 for r in rows if r.get("may_sob_percent") is not None)
    june_sob = sum(1 for r in rows if r.get("june_sob_percent") is not None)
    matched = _count_ytd_matched(master, ytd)
    return {
        "master_seller_count": len(master.sellers),
        "ytd_monthly_rows_loaded": ytd.stats.total_loaded,
        "ytd_matched_count": matched,
        "ytd_unmatched_count": len(master.sellers) - matched,
        "ytd_load_error": ytd.load_error,
        **tiktok_counts,
        "may_sob_calculated_count": may_sob,
        "june_sob_calculated_count": june_sob,
        "may_shopee_gmv_total": portfolio.get("may_shopee_gmv"),
        "june_shopee_gmv_total": portfolio.get("june_shopee_gmv"),
        "may_tiktok_gmv_total": portfolio.get("may_tiktok_gmv"),
        "june_tiktok_gmv_total": portfolio.get("june_tiktok_gmv"),
        "may_portfolio_sob_percent": portfolio.get("may_portfolio_sob_percent"),
        "june_portfolio_sob_percent": portfolio.get("june_portfolio_sob_percent"),
        "portfolio_sob_change_pp": portfolio.get("portfolio_sob_change_pp"),
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


def _historical_tiktok_targets(
    master: SellerMasterLoadResult | None = None,
) -> list[dict[str, Any]]:
    """
    Build FastMoss fetch targets for Historical SOB.

    Prefer merged Historical SOB rows when seller master is available; otherwise
    fall back to MAPPED rows in fastmoss_mapping.json (no Google Sheets required).
    """
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()

    if master is not None:
        try:
            ytd = get_ytd_monthly()
            merged_rows = build_historical_sob_rows(master, ytd=ytd)
            for row in merged_rows:
                fastmoss_id = str(row.get("fastmoss_shop_id") or "").strip()
                shop_id = str(row.get("shop_id") or "").strip()
                if not fastmoss_id or not shop_id or shop_id in seen:
                    continue
                if row.get("platform_source") == "SHOPEE_ONLY":
                    continue
                seen.add(shop_id)
                targets.append(
                    {
                        "shop_id": shop_id,
                        "fastmoss_shop_id": fastmoss_id,
                        "tiktok_shop_name": row.get("tiktok_shop_name"),
                    }
                )
            if targets:
                return targets
        except Exception as exc:
            logger.warning("Historical SOB target build via master failed: %s", exc)

    try:
        from seller.fastmoss.mapping import load_fastmoss_mapping
        from seller.fastmoss.review import allows_tiktok_data, get_review_by_shop_id
    except Exception as exc:
        logger.warning("Historical SOB mapping fallback unavailable: %s", exc)
        return targets

    try:
        payload = load_fastmoss_mapping()
    except OSError as exc:
        logger.warning("Could not load fastmoss_mapping.json: %s", exc)
        return targets

    for row in payload.get("mappings") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("mapping_status") or "").upper() != MAPPING_MAPPED:
            continue
        shop_id = str(row.get("shop_id") or "").strip()
        fastmoss_id = str(row.get("fastmoss_shop_id") or "").strip()
        if not shop_id or not fastmoss_id or shop_id in seen:
            continue
        review = get_review_by_shop_id(shop_id)
        review_status = str((review or {}).get("review_status") or "")
        # Include MAPPED rows; prefer APPROVED for TikTok display, but still fetch.
        if review_status and not allows_tiktok_data(review_status):
            # Still fetch so cache is ready once approved; include in targets.
            pass
        seen.add(shop_id)
        targets.append(
            {
                "shop_id": shop_id,
                "fastmoss_shop_id": fastmoss_id,
                "tiktok_shop_name": row.get("tiktok_shop_name") or row.get("fastmoss_shop_name"),
            }
        )
    return targets


def refresh_historical_sob_tiktok_cache(
    master: SellerMasterLoadResult | None = None,
    *,
    delay_sec: float = 0.35,
    force: bool = False,
) -> dict[str, Any]:
    """Fetch May/June TikTok GMV for mapped shops in the merged Historical SOB universe."""
    targets = _historical_tiktok_targets(master)

    cache = load_historical_sob_cache()
    shops: dict[str, Any] = dict(cache.get("shops") or {})
    fetched = 0
    failed = 0
    skipped = 0

    for index, row in enumerate(targets):
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
            and existing.get("may_gmv_php") is not None
            and existing.get("june_gmv_php") is not None
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
            if fetched % 5 == 0 or fetched == 1:
                cache["shops"] = shops
                save_historical_sob_cache(cache)
                logger.info(
                    "Historical TikTok progress %s/%s (last shop_id=%s may=%s june=%s)",
                    fetched,
                    len(targets),
                    shop_id,
                    collected.get("may_gmv_php"),
                    collected.get("june_gmv_php"),
                )
                print(
                    f"progress {fetched}/{len(targets)} shop={shop_id} "
                    f"may={collected.get('may_gmv_php')} june={collected.get('june_gmv_php')}",
                    flush=True,
                )
        except Exception as exc:
            logger.warning("Historical TikTok fetch failed for shop %s: %s", shop_id, exc)
            # Never wipe a previously successful May/June row (Railway WAF often fails).
            if (
                isinstance(existing, dict)
                and existing.get("status") == "success"
                and existing.get("may_gmv_php") is not None
                and existing.get("june_gmv_php") is not None
            ):
                logger.info(
                    "Preserving cached May/June GMV for shop %s after fetch failure",
                    shop_id,
                )
                failed += 1
                continue
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
        "approved_count": len(targets),
        "fetched_count": fetched,
        "failed_count": failed,
        "skipped_cached_count": max(0, len(targets) - fetched - failed - skipped),
        "cache_shop_count": len(shops),
        **counts,
    }


def refresh_historical_sob(*, force: bool = False) -> dict[str, Any]:
    """
    Refresh Historical SOB TikTok cache.

    Default ``force=False`` keeps existing May/June successes and only fills gaps
    so daily Update Data / Railway restarts do not re-scrape every shop.
    """
    master: SellerMasterLoadResult | None = None
    ytd = None
    try:
        master = get_seller_master(force_refresh=True)
        ytd = get_ytd_monthly(force_refresh=True)
    except Exception as exc:
        logger.warning("Historical SOB sheet reload skipped: %s", exc)

    tiktok_result = refresh_historical_sob_tiktok_cache(master, force=force)
    cache = load_historical_sob_cache()
    if master is not None and ytd is not None:
        rows = build_historical_sob_rows(master, ytd=ytd, tiktok_cache=cache)
        portfolio = build_portfolio_historical_sob(rows)
        summary = _summary_counts(rows, master, ytd=ytd, cache=cache, portfolio=portfolio)
    else:
        rows = []
        portfolio = {}
        summary = {**_tiktok_cache_counts(cache), "sheet_reload": "skipped"}
    return {
        "success": True,
        "refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": summary,
        "tiktok_cache": tiktok_result,
    }


def _build_payload(
    master: SellerMasterLoadResult,
    *,
    ytd: YtdMonthlyLoadResult,
    cache: dict[str, Any],
    warnings: list[str],
    sheet_filters: dict[str, Any] | None = None,
    category_mapping: dict[str, Any] | None = None,
    sla_update_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = build_historical_sob_rows(
        master,
        ytd=ytd,
        tiktok_cache=cache,
        category_mapping=category_mapping,
    )
    portfolio = build_portfolio_historical_sob(rows)
    summary = _summary_counts(rows, master, ytd=ytd, cache=cache, portfolio=portfolio)
    categories = sorted(
        {str(r.get("category") or "Uncategorized").strip() for r in rows},
        key=str.lower,
    )
    sheet_filters = sheet_filters or {}

    return {
        "version": "v1",
        "module": "historical_sob",
        "status": "ok",
        "master_currency": "USD",
        "shopee_currency": "USD",
        "tiktok_source_currency": "PHP",
        "usd_php_rate": USD_PHP_RATE,
        "master_tab": master.tab,
        "ytd_tab": ytd.tab,
        "periods": dict(HISTORICAL_PERIODS),
        "cache_updated_at": cache.get("updated_at"),
        "warnings": warnings,
        "summary": summary,
        "kpis": {
            "total_shops": len(master.sellers),
            "may_portfolio_gmv": portfolio.get("may_total_gmv"),
            "june_portfolio_gmv": portfolio.get("june_total_gmv"),
            "may_shopee_gmv": portfolio.get("may_shopee_gmv"),
            "may_tiktok_gmv": portfolio.get("may_tiktok_gmv"),
            "may_shopee_sob_percent": portfolio.get("may_shopee_sob_percent"),
            "may_tiktok_sob_percent": portfolio.get("may_tiktok_sob_percent"),
            "may_portfolio_sob_percent": portfolio.get("may_portfolio_sob_percent"),
            "june_shopee_gmv": portfolio.get("june_shopee_gmv"),
            "june_tiktok_gmv": portfolio.get("june_tiktok_gmv"),
            "june_shopee_sob_percent": portfolio.get("june_shopee_sob_percent"),
            "june_tiktok_sob_percent": portfolio.get("june_tiktok_sob_percent"),
            "june_portfolio_sob_percent": portfolio.get("june_portfolio_sob_percent"),
            "portfolio_sob_change_pp": portfolio.get("portfolio_sob_change_pp"),
        },
        "portfolio": portfolio,
        "sellers": rows,
        "na_preview": _na_preview(rows),
        "sheet_filters": sheet_filters,
        "rm_filter": sheet_filters.get("rm_filter"),
        "gp_filter": sheet_filters.get("gp_filter"),
        "category_mapping": category_mapping or {},
        "sla_update_state": sla_update_state or {},
        "filters": {
            "mapping_statuses": sorted({str(r.get("fastmoss_match_status")) for r in rows}),
            "categories": categories,
        },
    }


def _empty_payload(*, master: SellerMasterLoadResult | None, error: str) -> dict[str, Any]:
    return {
        "version": "v1",
        "module": "historical_sob",
        "status": "degraded",
        "master_currency": "USD",
        "shopee_currency": "USD",
        "tiktok_source_currency": "PHP",
        "usd_php_rate": USD_PHP_RATE,
        "master_tab": getattr(master, "tab", "shpoee link"),
        "ytd_tab": get_ytd_monthly().tab,
        "warnings": [error],
        "summary": {
            "master_seller_count": len(master.sellers) if master else 0,
            "ytd_monthly_rows_loaded": 0,
            "tiktok_historical_fetched_count": 0,
            "tiktok_may_gmv_fetched_count": 0,
            "tiktok_june_gmv_fetched_count": 0,
            "may_sob_calculated_count": 0,
            "june_sob_calculated_count": 0,
        },
        "kpis": {
            "total_shops": len(master.sellers) if master else 0,
            "may_shopee_gmv": None,
            "may_tiktok_gmv": None,
            "may_portfolio_sob_percent": None,
            "june_shopee_gmv": None,
            "june_tiktok_gmv": None,
            "june_portfolio_sob_percent": None,
            "portfolio_sob_change_pp": None,
        },
        "portfolio": {},
        "sellers": [],
        "na_preview": [],
        "filters": {"mapping_statuses": []},
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

        if ytd.load_error and ytd.stats.total_loaded == 0:
            from seller.intelligence.historical_sob.ytd_monthly import clear_ytd_monthly_cache

            clear_ytd_monthly_cache()
            ytd = get_ytd_monthly(force_refresh=True)

        if ytd.load_error:
            warnings.append(ytd.load_error)
        if ytd.stats.total_loaded == 0:
            warnings.append(
                "No rows loaded from ytd monthly data — Shopee GMV will show N/A until the tab is available."
            )
        elif _count_ytd_matched(master, ytd) == 0:
            warnings.append(
                "ytd monthly data loaded but no shop_id matches to shpoee link — check shop_id / shop_name."
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
                "TikTok May/June GMV not cached yet — run Update Data on Seller Level Analysis once."
            )

        from seller.intelligence.business.sla_update_state import get_sla_update_state_for_api
        from seller.intelligence.category_raw import get_category_mapping_payload
        from seller.intelligence.gp_shop_rm import get_sla_sheet_filters_payload

        sheet_filters = get_sla_sheet_filters_payload()
        category_mapping = get_category_mapping_payload()
        return _build_payload(
            master,
            ytd=ytd,
            cache=cache,
            warnings=warnings,
            sheet_filters=sheet_filters,
            category_mapping=category_mapping,
            sla_update_state=get_sla_update_state_for_api(),
        )
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
