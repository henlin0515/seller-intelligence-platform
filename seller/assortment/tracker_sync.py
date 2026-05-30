from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from seller.assortment.catalog_fetch import fetch_tracker_row_catalogs
from seller.assortment.db import get_session
from seller.assortment.import_service import import_competitor_products
from seller.assortment.matching import run_matching_for_all_competitors
from seller.assortment.models import TrackerFetchStatus
from seller.assortment.service import competitor_data_available
from seller.competitor_tracker.constants import COMPETITOR_TAB_NAME
from seller.competitor_tracker.sheet import load_competitors_from_sheet

logger = logging.getLogger("seller.assortment.tracker_sync")


def _status_label(side: dict[str, Any]) -> str:
    return "OK" if side.get("status") == "ok" else "NA"


def _row_from_fetch(sheet_row: dict[str, str], fetch_out: dict[str, Any]) -> dict[str, Any]:
    shopee = fetch_out.get("shopee") or {}
    tiktok = fetch_out.get("tiktok") or {}
    shopee_link = (sheet_row.get("shopee_link") or "").strip() or "NA"
    tiktok_link = (sheet_row.get("tiktok_link") or "").strip() or "NA"
    return {
        "row_number": sheet_row.get("row_number"),
        "seller_id": sheet_row.get("shop_id") or "",
        "seller_name": sheet_row.get("shop_name") or "",
        "shopee_link": shopee_link,
        "tiktok_link": tiktok_link,
        "shopee_status": _status_label(shopee),
        "tiktok_status": _status_label(tiktok),
        "shopee_reason": shopee.get("reason") if shopee.get("status") != "ok" else None,
        "tiktok_reason": tiktok.get("reason") if tiktok.get("status") != "ok" else None,
        "shopee_products_found": shopee.get("product_count", 0),
        "tiktok_products_found": tiktok.get("product_count", 0),
        "products_found_total": len(fetch_out.get("products") or []),
        "comparison": fetch_out.get("comparison") or {},
        "link_results": fetch_out.get("link_results") or [],
        "catalog_status": fetch_out.get("status") or "na",
    }


def _tracker_row_to_api(sheet_row: dict[str, str], status: TrackerFetchStatus | None) -> dict[str, Any]:
    shopee = (sheet_row.get("shopee_link") or "").strip()
    tiktok = (sheet_row.get("tiktok_link") or "").strip()
    base: dict[str, Any] = {
        "row_number": sheet_row.get("row_number"),
        "seller_id": sheet_row.get("shop_id") or "",
        "seller_name": sheet_row.get("shop_name") or sheet_row.get("shop_id") or "",
        "shopee_link": shopee or "NA",
        "tiktok_link": tiktok or "NA",
    }
    if status:
        try:
            stored = json.loads(status.link_results_json or "{}")
        except json.JSONDecodeError:
            stored = {}
        if isinstance(stored, dict) and stored.get("row_number"):
            base.update(stored)
            base["last_sync_at"] = status.last_sync_at.isoformat() if status.last_sync_at else None
            return base
        try:
            links = json.loads(status.link_results_json or "[]")
        except json.JSONDecodeError:
            links = []
        shopee_side = next((x for x in links if x.get("link_type") == "shopee"), {})
        tiktok_side = next((x for x in links if x.get("link_type") == "tiktok"), {})
        base.update(
            {
                "shopee_status": "OK" if shopee_side.get("status") == "ok" else "NA",
                "tiktok_status": "OK" if tiktok_side.get("status") == "ok" else "NA",
                "shopee_reason": shopee_side.get("reason"),
                "tiktok_reason": tiktok_side.get("reason"),
                "shopee_products_found": shopee_side.get("product_count", 0),
                "tiktok_products_found": tiktok_side.get("product_count", 0),
                "products_found_total": status.product_count,
                "link_results": links,
                "last_sync_at": status.last_sync_at.isoformat() if status.last_sync_at else None,
            }
        )
    else:
        base.update(
            {
                "shopee_status": "NA",
                "tiktok_status": "NA",
                "shopee_reason": "Not synced yet." if shopee else "No Shopee link in Column C.",
                "tiktok_reason": "Not synced yet." if tiktok else "No TikTok link in Column D.",
                "shopee_products_found": 0,
                "tiktok_products_found": 0,
                "products_found_total": 0,
                "link_results": [],
                "last_sync_at": None,
            }
        )
    return base


def get_tracker_payload() -> dict[str, Any]:
    """COMPETITOR_TRACKER via same Google Sheets client as Voucher Tracker."""
    rows, meta = load_competitors_from_sheet()
    session = get_session()
    try:
        status_map = {s.seller_id: s for s in session.query(TrackerFetchStatus).all()}
        sellers = [_tracker_row_to_api(r, status_map.get(r.get("shop_id") or "")) for r in rows]
        configured = meta.get("configured", False)
        sheet_error = meta.get("error")
        tab_has_no_rows = configured and sheet_error is None and len(rows) == 0
        return {
            "ok": sheet_error is None,
            "configured": configured,
            "tab": meta.get("tab") or COMPETITOR_TAB_NAME,
            "sheet_error": sheet_error,
            "tab_empty": tab_has_no_rows,
            "tab_empty_message": (
                f"No rows with Column C or D links in {COMPETITOR_TAB_NAME}."
                if tab_has_no_rows
                else None
            ),
            "row_count": len(rows),
            "has_competitor_data": competitor_data_available(session),
            "sellers": sellers,
        }
    finally:
        session.close()


def _upsert_fetch_status(
    session,
    *,
    seller_id: str,
    seller_name: str,
    shopee_link: str,
    tiktok_link: str,
    row_payload: dict[str, Any],
) -> None:
    now = datetime.now(timezone.utc)
    row = session.query(TrackerFetchStatus).filter(TrackerFetchStatus.seller_id == seller_id).first()
    if not row:
        row = TrackerFetchStatus(seller_id=seller_id)
        session.add(row)
    row.seller_name = seller_name
    row.shopee_link = shopee_link or None
    row.tiktok_link = tiktok_link or None
    row.catalog_status = row_payload.get("catalog_status") or "na"
    reasons = []
    if row_payload.get("shopee_reason"):
        reasons.append(f"Shopee: {row_payload['shopee_reason']}")
    if row_payload.get("tiktok_reason"):
        reasons.append(f"TikTok: {row_payload['tiktok_reason']}")
    row.catalog_reason = "; ".join(reasons) if reasons else None
    row.product_count = row_payload.get("products_found_total", 0)
    row.shop_link_attempted = row_payload.get("shopee_link") if row_payload.get("shopee_link") != "NA" else row_payload.get("tiktok_link")
    row.link_results_json = json.dumps(row_payload, ensure_ascii=False)
    row.last_sync_at = now


def sync_tracker_catalog(*, run_matching: bool = True) -> dict[str, Any]:
    """
    Read COMPETITOR_TRACKER (Column C + D per row), fetch each side, compare, import merged catalog.
    """
    rows, meta = load_competitors_from_sheet()
    results: list[dict[str, Any]] = []
    imported_total = 0
    ok_count = na_count = 0

    if meta.get("error") and not rows:
        return {
            "ok": False,
            "sheet": meta,
            "processed": 0,
            "catalog_ok": 0,
            "catalog_na": 0,
            "products_imported": 0,
            "has_competitor_data": competitor_data_available(),
            "matching": None,
            "results": [],
            "message": meta.get("error"),
        }

    session = get_session()
    try:
        for sheet_row in rows:
            seller_id = sheet_row.get("shop_id") or ""
            seller_name = sheet_row.get("shop_name") or seller_id
            shopee = (sheet_row.get("shopee_link") or "").strip()
            tiktok = (sheet_row.get("tiktok_link") or "").strip()

            try:
                fetch_out = fetch_tracker_row_catalogs(shopee_link=shopee, tiktok_link=tiktok)
            except Exception as exc:
                logger.exception("Fetch failed for row %s", sheet_row.get("row_number"))
                fetch_out = {
                    "status": "na",
                    "reason": str(exc),
                    "products": [],
                    "shopee": {
                        "status": "na",
                        "reason": f"Unable to access competitor store ({exc}).",
                        "products": [],
                        "product_count": 0,
                        "shop_link": shopee or "NA",
                    },
                    "tiktok": {
                        "status": "na",
                        "reason": f"Unable to access competitor store ({exc}).",
                        "products": [],
                        "product_count": 0,
                        "shop_link": tiktok or "NA",
                    },
                    "comparison": {},
                    "link_results": [],
                }

            row_payload = _row_from_fetch(sheet_row, fetch_out)
            products = fetch_out.get("products") or []

            if products:
                try:
                    imp = import_competitor_products(
                        products,
                        label="tracker-sync",
                        competitor_shop_id=seller_id,
                        competitor_shop_name=seller_name,
                        mark_as_new=True,
                    )
                    imported_total += imp.get("imported", 0)
                    ok_count += 1
                except Exception as exc:
                    logger.exception("Import failed for seller %s", seller_id)
                    row_payload["catalog_status"] = "na"
                    row_payload["import_error"] = str(exc)
                    na_count += 1
            else:
                na_count += 1
                if not shopee:
                    row_payload["shopee_reason"] = row_payload.get("shopee_reason") or "No Shopee link in Column C."
                if not tiktok:
                    row_payload["tiktok_reason"] = row_payload.get("tiktok_reason") or "No TikTok link in Column D."

            _upsert_fetch_status(
                session,
                seller_id=seller_id,
                seller_name=seller_name,
                shopee_link=shopee,
                tiktok_link=tiktok,
                row_payload=row_payload,
            )

            for side, label in ((row_payload.get("shopee_reason"), "Shopee"), (row_payload.get("tiktok_reason"), "TikTok")):
                if side:
                    logger.info(
                        "Tracker row %s %s NA: %s",
                        row_payload.get("row_number"),
                        label,
                        side,
                    )

            results.append(row_payload)

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    matching_stats = None
    if run_matching and imported_total > 0:
        try:
            matching_stats = run_matching_for_all_competitors()
        except Exception as exc:
            logger.exception("Matching after tracker sync failed")
            matching_stats = {"error": str(exc)}

    tab_has_no_rows = meta.get("error") is None and len(rows) == 0
    return {
        "ok": meta.get("error") is None,
        "sheet": meta,
        "tab": COMPETITOR_TAB_NAME,
        "tab_empty": tab_has_no_rows,
        "processed": len(rows),
        "catalog_ok": ok_count,
        "catalog_na": na_count,
        "products_imported": imported_total,
        "has_competitor_data": competitor_data_available(),
        "matching": matching_stats,
        "results": results,
    }
