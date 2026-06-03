"""Business Intelligence V1 — seller master + FastMoss TikTok data."""

from __future__ import annotations

from typing import Any

from seller.fastmoss.mapping import MAPPING_NOT_FOUND, load_fastmoss_mapping
from seller.fastmoss.review import (
    REVIEW_APPROVED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    allows_tiktok_data,
    get_review_by_shop_id,
)
from seller.intelligence.business.calculations import mom_percent, sob_pair, tiktok_php_to_usd
from seller.intelligence.business.store import (
    fastmoss_collection_by_shop_id,
    load_business_intelligence_data,
)
from seller.intelligence.business.shopee_adgmv import (
    ShopeeAdgmvRecord,
    ShopeeAdgmvLoadResult,
    get_shopee_adgmv,
    match_shopee_adgmv_to_shop_name,
)
from seller.intelligence.gp_shop_rm import normalize_shop_key
from seller.intelligence.platform_extra_shops import PlatformSource, try_load_platform_extra_shops
from seller.intelligence.seller_master import SellerMasterLoadResult, get_seller_master

SHOPEE_NA_REASON = "Shopee ADGMV not found in Tracker"
SOB_NA_REASON = "SOB requires Shopee and TikTok ADGMV"
TIKTOK_ONLY_SHOPEE_NA = "TikTok-only shop — no Shopee ADGMV"
SHOPEE_ONLY_TIKTOK_NA = "Shopee-only shop — no TikTok ADGMV"


def _round_sob(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 1)


def _period_sob(
    shopee_usd: float | None,
    tiktok_usd: float | None,
    *,
    platform_source: PlatformSource,
) -> tuple[float | None, float | None]:
    """Row-level SOB; single-platform shops use 100% / 0% when GMV > 0."""
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


def _apply_sob_data(record: dict[str, Any], *, platform_source: PlatformSource = "NORMAL") -> None:
    shopee_mtd = record.get("shopee_mtd_adgmv_usd")
    shopee_m1 = record.get("shopee_m1_adgmv_usd")
    tiktok_mtd = record.get("tiktok_mtd_adgmv_usd")
    tiktok_m1 = record.get("tiktok_m1_adgmv_usd")

    mtd_calculated = False
    m1_calculated = False

    mtd_shopee, mtd_tiktok = _period_sob(shopee_mtd, tiktok_mtd, platform_source=platform_source)
    if mtd_shopee is not None and mtd_tiktok is not None:
        record["mtd_shopee_sob_percent"] = _round_sob(mtd_shopee)
        record["mtd_tiktok_sob_percent"] = _round_sob(mtd_tiktok)
        mtd_calculated = True

    m1_shopee, m1_tiktok = _period_sob(shopee_m1, tiktok_m1, platform_source=platform_source)
    if m1_shopee is not None and m1_tiktok is not None:
        record["m1_shopee_sob_percent"] = _round_sob(m1_shopee)
        record["m1_tiktok_sob_percent"] = _round_sob(m1_tiktok)
        m1_calculated = True

    if mtd_calculated or m1_calculated:
        record["sob_na_reason"] = None
        record["sob_data_status"] = (
            "available" if mtd_calculated and m1_calculated else "partial"
        )
        return

    record["sob_data_status"] = "na"
    record["sob_na_reason"] = SOB_NA_REASON


def _fastmoss_mapping_indexes() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    try:
        payload = load_fastmoss_mapping()
    except OSError:
        return {}, {}
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    rank = {"MAPPED": 3, "NEED_REVIEW": 2, "NOT_FOUND": 1}
    for row in payload.get("mappings") or []:
        if not isinstance(row, dict):
            continue
        shop_id = str(row.get("shop_id") or "").strip()
        if shop_id:
            by_id[shop_id] = row
        for raw in (row.get("shop_name"), row.get("tiktok_shop_name")):
            key = normalize_shop_key(str(raw or ""))
            if not key:
                continue
            prev = by_name.get(key)
            if prev is None or rank.get(str(row.get("mapping_status") or "").upper(), 0) >= rank.get(
                str(prev.get("mapping_status") or "").upper(), 0
            ):
                by_name[key] = row
    return by_id, by_name


def resolve_fastmoss_mapping_row(
    *,
    shop_id: str,
    shop_name: str,
    tiktok_shop_name: str,
    by_id: dict[str, dict[str, Any]],
    by_name: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    sid = str(shop_id or "").strip()
    if sid and sid in by_id:
        return by_id[sid]
    for raw in (shop_name, tiktok_shop_name):
        key = normalize_shop_key(str(raw or ""))
        if key and key in by_name:
            return by_name[key]
    return None


def _fastmoss_collection_indexes(
    data: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id = fastmoss_collection_by_shop_id(data)
    by_name: dict[str, dict[str, Any]] = {}
    for row in by_id.values():
        for raw in (row.get("tiktok_shop_name"), row.get("shop_name")):
            key = normalize_shop_key(str(raw or ""))
            if key:
                by_name[key] = row
    return by_id, by_name


def resolve_fastmoss_collection_row(
    *,
    shop_id: str,
    shop_name: str,
    tiktok_shop_name: str,
    by_id: dict[str, dict[str, Any]],
    by_name: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    sid = str(shop_id or "").strip()
    if sid and sid in by_id:
        return by_id[sid]
    for raw in (tiktok_shop_name, shop_name):
        key = normalize_shop_key(str(raw or ""))
        if key and key in by_name:
            return by_name[key]
    return None


def _tiktok_na_reason(
    mapping_status: str | None,
    collection_row: dict[str, Any] | None,
    review_status: str | None = None,
) -> str:
    if mapping_status != "MAPPED":
        return "FastMoss shop not mapped"
    rs = str(review_status or "").upper()
    if rs == REVIEW_PENDING:
        return "FastMoss mapping pending review"
    if rs == REVIEW_REJECTED:
        return "FastMoss mapping rejected"
    if rs and rs != REVIEW_APPROVED:
        return "FastMoss mapping not approved"
    if collection_row is None:
        return "TikTok data not collected"
    if collection_row.get("status") != "success":
        return str(collection_row.get("error") or "FastMoss collection failed")
    return "TikTok data unavailable"


def _apply_tiktok_data(
    record: dict[str, Any],
    *,
    mapping_status: str,
    collection_row: dict[str, Any] | None,
    review_status: str | None = None,
) -> None:
    if not allows_tiktok_data(review_status):
        record["tiktok_data_status"] = "na"
        record["tiktok_na_reason"] = _tiktok_na_reason(
            mapping_status,
            collection_row,
            review_status,
        )
        return

    if collection_row and collection_row.get("status") == "success":
        mtd_gmv = float(collection_row.get("mtd_gmv_php") or 0)
        m1_gmv = float(collection_row.get("m1_gmv_php") or 0)
        mtd_adgmv_php = float(collection_row.get("tiktok_mtd_adgmv_php") or 0)
        m1_adgmv_php = float(collection_row.get("tiktok_m1_adgmv_php") or 0)
        mtd_adgmv_usd = tiktok_php_to_usd(mtd_adgmv_php)
        m1_adgmv_usd = tiktok_php_to_usd(m1_adgmv_php)
        record.update(
            {
                "tiktok_mtd_gmv_php": round(mtd_gmv, 2),
                "tiktok_m1_gmv_php": round(m1_gmv, 2),
                "tiktok_mtd_adgmv_php": round(mtd_adgmv_php, 4),
                "tiktok_m1_adgmv_php": round(m1_adgmv_php, 4),
                "tiktok_mtd_adgmv_usd": round(mtd_adgmv_usd, 4),
                "tiktok_m1_adgmv_usd": round(m1_adgmv_usd, 4),
                "tiktok_mom_percent": (
                    round(mom, 4)
                    if (mom := mom_percent(mtd_adgmv_usd, m1_adgmv_usd)) is not None
                    else None
                ),
                "tiktok_data_status": "available",
                "tiktok_na_reason": None,
            }
        )
        return

    record["tiktok_na_reason"] = _tiktok_na_reason(
        mapping_status,
        collection_row,
        review_status,
    )


def _apply_shopee_data(
    record: dict[str, Any],
    *,
    shopee_row: ShopeeAdgmvRecord | None,
) -> None:
    if shopee_row is None:
        record["shopee_data_status"] = "na"
        record["tracker_shop_name"] = None
        record["shopee_na_reason"] = SHOPEE_NA_REASON
        return

    record.update(
        {
            "tracker_shop_name": shopee_row.tracker_shop_name,
            "shopee_mtd_adgmv_usd": round(shopee_row.mtd_adgmv_usd, 4),
            "shopee_m1_adgmv_usd": round(shopee_row.m1_adgmv_usd, 4),
            "shopee_mom_percent": (
                round(mom, 4)
                if (mom := mom_percent(shopee_row.mtd_adgmv_usd, shopee_row.m1_adgmv_usd)) is not None
                else None
            ),
            "shopee_data_status": "available",
            "shopee_na_reason": None,
        }
    )


def build_business_seller_record(
    *,
    shop_id: str,
    shop_name: str,
    tiktok_shop_name: str,
    mapping_row: dict[str, Any] | None,
    collection_row: dict[str, Any] | None,
    shopee_row: ShopeeAdgmvRecord | None = None,
    platform_source: PlatformSource = "NORMAL",
    gp_shop_id: str | None = None,
    gp_shop_name: str | None = None,
    rm: str | None = None,
    shopee_link: str = "",
) -> dict[str, Any]:
    mapping_status = str((mapping_row or {}).get("mapping_status") or MAPPING_NOT_FOUND)
    fastmoss_matched_shop = (mapping_row or {}).get("fastmoss_shop_name")
    review_row = get_review_by_shop_id(shop_id)
    review_status = str((review_row or {}).get("review_status") or "")
    effective_collection = (
        collection_row
        if allows_tiktok_data(review_status)
        else None
    )

    record: dict[str, Any] = {
        "shop_id": shop_id,
        "shop_name": shop_name,
        "shopee_link": shopee_link,
        "tiktok_shop_name": tiktok_shop_name,
        "platform_source": platform_source,
        "gp_shop_id": gp_shop_id,
        "gp_shop_name": gp_shop_name,
        "rm": rm,
        "fastmoss_match_status": mapping_status,
        "fastmoss_matched_shop": fastmoss_matched_shop,
        "fastmoss_review_status": review_status or None,
        "fastmoss_audit_status": (review_row or {}).get("audit_status"),
        "fastmoss_mapping_confidence": (mapping_row or {}).get("confidence"),
        "tracker_shop_name": None,
        "tiktok_mtd_gmv_php": None,
        "tiktok_m1_gmv_php": None,
        "tiktok_mtd_adgmv_php": None,
        "tiktok_m1_adgmv_php": None,
        "tiktok_mtd_adgmv_usd": None,
        "tiktok_m1_adgmv_usd": None,
        "tiktok_mom_percent": None,
        "tiktok_data_status": "na",
        "tiktok_na_reason": None,
        "shopee_mtd_adgmv_usd": None,
        "shopee_m1_adgmv_usd": None,
        "shopee_mom_percent": None,
        "shopee_data_status": "na",
        "shopee_na_reason": SHOPEE_NA_REASON,
        "mtd_shopee_sob_percent": None,
        "mtd_tiktok_sob_percent": None,
        "m1_shopee_sob_percent": None,
        "m1_tiktok_sob_percent": None,
        "sob_data_status": "na",
        "sob_na_reason": SOB_NA_REASON,
    }

    if platform_source == "SHOPEE_ONLY":
        record["tiktok_data_status"] = "na"
        record["tiktok_na_reason"] = SHOPEE_ONLY_TIKTOK_NA
    elif platform_source == "TIKTOK_ONLY":
        record["shopee_data_status"] = "na"
        record["shopee_na_reason"] = TIKTOK_ONLY_SHOPEE_NA
        record["tracker_shop_name"] = None

    if platform_source != "SHOPEE_ONLY":
        _apply_tiktok_data(
            record,
            mapping_status=mapping_status,
            collection_row=effective_collection,
            review_status=review_status,
        )
    if platform_source != "TIKTOK_ONLY":
        _apply_shopee_data(record, shopee_row=shopee_row)
    _apply_sob_data(record, platform_source=platform_source)
    return record


def _merge_gp_metadata(record: dict[str, Any], *, gp_shop_id: str, gp_shop_name: str, rm: str) -> None:
    if gp_shop_id and not record.get("gp_shop_id"):
        record["gp_shop_id"] = gp_shop_id
    if gp_shop_name and not record.get("gp_shop_name"):
        record["gp_shop_name"] = gp_shop_name
    if rm and not record.get("rm"):
        record["rm"] = rm


def _seller_keys(shop_name: str, tiktok_shop_name: str) -> list[str]:
    return [k for k in (normalize_shop_key(shop_name), normalize_shop_key(tiktok_shop_name)) if k]


def _find_existing_index(
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


def build_merged_business_seller_rows(
    master: SellerMasterLoadResult,
    *,
    shopee_adgmv: ShopeeAdgmvLoadResult | None = None,
) -> list[dict[str, Any]]:
    """Union of shpoee link + shopee shop only + tiktok shop only (deduped)."""
    from seller.fastmoss.review import ensure_review_store_synced

    ensure_review_store_synced()
    tracker = shopee_adgmv or get_shopee_adgmv()
    saved = load_business_intelligence_data()
    collection_by_id, collection_by_name = _fastmoss_collection_indexes(saved)
    mapping_by_id, mapping_by_name = _fastmoss_mapping_indexes()
    shopee_only, tiktok_only = try_load_platform_extra_shops()

    by_id: dict[str, dict[str, Any]] = {}
    by_name_key: dict[str, str] = {}

    def register(record: dict[str, Any]) -> None:
        sid = str(record["shop_id"])
        by_id[sid] = record
        for key in _seller_keys(record.get("shop_name", ""), record.get("tiktok_shop_name", "")):
            by_name_key[key] = sid

    for seller in master.sellers:
        mapping_row = resolve_fastmoss_mapping_row(
            shop_id=seller.shop_id,
            shop_name=seller.shop_name,
            tiktok_shop_name=seller.tiktok_shop_name,
            by_id=mapping_by_id,
            by_name=mapping_by_name,
        )
        collection_row = resolve_fastmoss_collection_row(
            shop_id=seller.shop_id,
            shop_name=seller.shop_name,
            tiktok_shop_name=seller.tiktok_shop_name,
            by_id=collection_by_id,
            by_name=collection_by_name,
        )
        register(
            build_business_seller_record(
                shop_id=seller.shop_id,
                shop_name=seller.shop_name,
                tiktok_shop_name=seller.tiktok_shop_name,
                shopee_link=seller.shopee_link,
                mapping_row=mapping_row,
                collection_row=collection_row,
                shopee_row=match_shopee_adgmv_to_shop_name(seller.shop_name, tracker),
                platform_source="NORMAL",
            )
        )

    for extra in shopee_only.rows:
        existing_id = _find_existing_index(
            shop_id=extra.shop_id,
            shop_name=extra.shop_name,
            tiktok_shop_name="",
            by_id=by_id,
            by_name_key=by_name_key,
        )
        if existing_id:
            _merge_gp_metadata(
                by_id[existing_id],
                gp_shop_id=extra.gp_shop_id,
                gp_shop_name=extra.gp_shop_name,
                rm=extra.rm,
            )
            continue

        mapping_row = resolve_fastmoss_mapping_row(
            shop_id=extra.shop_id,
            shop_name=extra.shop_name,
            tiktok_shop_name="",
            by_id=mapping_by_id,
            by_name=mapping_by_name,
        )
        shopee_row = match_shopee_adgmv_to_shop_name(extra.shop_name, tracker)
        if shopee_row is None and extra.gp_shop_name:
            shopee_row = match_shopee_adgmv_to_shop_name(extra.gp_shop_name, tracker)
        register(
            build_business_seller_record(
                shop_id=extra.shop_id,
                shop_name=extra.shop_name,
                tiktok_shop_name="",
                mapping_row=mapping_row,
                collection_row=None,
                shopee_row=shopee_row,
                platform_source="SHOPEE_ONLY",
                gp_shop_id=extra.gp_shop_id,
                gp_shop_name=extra.gp_shop_name,
                rm=extra.rm,
            )
        )

    for extra in tiktok_only.rows:
        sid = extra.synthetic_shop_id
        existing_id = _find_existing_index(
            shop_id=sid,
            shop_name="",
            tiktok_shop_name=extra.tiktok_shop_name,
            by_id=by_id,
            by_name_key=by_name_key,
        )
        if existing_id:
            rec = by_id[existing_id]
            _merge_gp_metadata(
                rec,
                gp_shop_id=extra.gp_shop_id,
                gp_shop_name=extra.gp_shop_name,
                rm="",
            )
            if rec.get("platform_source") == "SHOPEE_ONLY" and not rec.get("tiktok_shop_name"):
                rec["tiktok_shop_name"] = extra.tiktok_shop_name
                mapping_row = resolve_fastmoss_mapping_row(
                    shop_id=rec["shop_id"],
                    shop_name=rec.get("shop_name", ""),
                    tiktok_shop_name=extra.tiktok_shop_name,
                    by_id=mapping_by_id,
                    by_name=mapping_by_name,
                )
                if mapping_row:
                    rec["fastmoss_match_status"] = str(
                        mapping_row.get("mapping_status") or MAPPING_NOT_FOUND
                    )
                    rec["fastmoss_matched_shop"] = mapping_row.get("fastmoss_shop_name")
                collection_row = resolve_fastmoss_collection_row(
                    shop_id=rec["shop_id"],
                    shop_name=rec.get("shop_name", ""),
                    tiktok_shop_name=extra.tiktok_shop_name,
                    by_id=collection_by_id,
                    by_name=collection_by_name,
                )
                review_row = get_review_by_shop_id(rec["shop_id"])
                review_status = str((review_row or {}).get("review_status") or "")
                _apply_tiktok_data(
                    rec,
                    mapping_status=str(rec.get("fastmoss_match_status") or MAPPING_NOT_FOUND),
                    collection_row=(
                        collection_row if allows_tiktok_data(review_status) else None
                    ),
                    review_status=review_status,
                )
                rec["platform_source"] = "NORMAL"
                _apply_sob_data(rec, platform_source="NORMAL")
            continue

        mapping_row = resolve_fastmoss_mapping_row(
            shop_id=sid,
            shop_name="",
            tiktok_shop_name=extra.tiktok_shop_name,
            by_id=mapping_by_id,
            by_name=mapping_by_name,
        )
        collection_row = resolve_fastmoss_collection_row(
            shop_id=sid,
            shop_name="",
            tiktok_shop_name=extra.tiktok_shop_name,
            by_id=collection_by_id,
            by_name=collection_by_name,
        )
        register(
            build_business_seller_record(
                shop_id=sid,
                shop_name=extra.gp_shop_name or extra.tiktok_shop_name,
                tiktok_shop_name=extra.tiktok_shop_name,
                mapping_row=mapping_row,
                collection_row=collection_row,
                shopee_row=None,
                platform_source="TIKTOK_ONLY",
                gp_shop_id=extra.gp_shop_id,
                gp_shop_name=extra.gp_shop_name,
            )
        )

    return list(by_id.values())


def get_business_intelligence_payload(
    master: SellerMasterLoadResult | None = None,
    shopee_adgmv: ShopeeAdgmvLoadResult | None = None,
) -> list[dict[str, Any]]:
    """Return BI seller rows with TikTok FastMoss + Shopee Tracker ADGMV."""
    from seller.fastmoss.review import ensure_review_store_synced

    loaded = master or get_seller_master()
    return build_merged_business_seller_rows(loaded, shopee_adgmv=shopee_adgmv)


def get_shopee_adgmv_match_summary(
    master: SellerMasterLoadResult | None = None,
    shopee_adgmv: ShopeeAdgmvLoadResult | None = None,
) -> dict[str, Any]:
    loaded = master or get_seller_master()
    tracker = shopee_adgmv or get_shopee_adgmv()
    matched = 0
    unmatched = 0
    for seller in loaded.sellers:
        if match_shopee_adgmv_to_shop_name(seller.shop_name, tracker):
            matched += 1
        else:
            unmatched += 1
    return {
        "tab": tracker.tab,
        "total_tracker_rows": tracker.stats.total_rows_read,
        "total_tracker_shops": tracker.stats.total_loaded,
        "total_matched_shops": matched,
        "total_unmatched_shops": unmatched,
        "import": tracker.stats.as_dict(),
    }


def validate_sob_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate MTD/M-1 SOB pairs sum to 100% where calculated."""
    calculated_rows = 0
    mtd_checked = 0
    m1_checked = 0
    mtd_failures: list[dict[str, Any]] = []
    m1_failures: list[dict[str, Any]] = []

    for row in rows:
        shop_name = row.get("shop_name")
        mtd_sh = row.get("mtd_shopee_sob_percent")
        mtd_tk = row.get("mtd_tiktok_sob_percent")
        if mtd_sh is not None and mtd_tk is not None:
            mtd_checked += 1
            total = mtd_sh + mtd_tk
            if abs(total - 100.0) > 0.05:
                mtd_failures.append(
                    {"shop_name": shop_name, "total": round(total, 2), "shopee": mtd_sh, "tiktok": mtd_tk}
                )

        m1_sh = row.get("m1_shopee_sob_percent")
        m1_tk = row.get("m1_tiktok_sob_percent")
        if m1_sh is not None and m1_tk is not None:
            m1_checked += 1
            total = m1_sh + m1_tk
            if abs(total - 100.0) > 0.05:
                m1_failures.append(
                    {"shop_name": shop_name, "total": round(total, 2), "shopee": m1_sh, "tiktok": m1_tk}
                )

        if row.get("sob_data_status") in ("available", "partial"):
            calculated_rows += 1

    return {
        "total_rows": len(rows),
        "total_rows_calculated": calculated_rows,
        "mtd_pairs_checked": mtd_checked,
        "m1_pairs_checked": m1_checked,
        "mtd_passed": mtd_checked - len(mtd_failures),
        "m1_passed": m1_checked - len(m1_failures),
        "mtd_failures": mtd_failures,
        "m1_failures": m1_failures,
        "passed": not mtd_failures and not m1_failures,
    }


def get_business_intelligence_meta() -> dict[str, Any]:
    saved = load_business_intelligence_data()
    if not saved:
        return {
            "fastmoss_connected": False,
            "data_file": None,
            "generated_at": None,
            "summary": None,
        }
    return {
        "fastmoss_connected": True,
        "data_file": "business_intelligence_data.json",
        "generated_at": saved.get("generated_at"),
        "reference_today": saved.get("reference_today"),
        "summary": saved.get("summary"),
        "source": saved.get("source"),
    }
