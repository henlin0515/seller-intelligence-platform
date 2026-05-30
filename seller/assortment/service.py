from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from seller.assortment.constants import (
    MATCH_CONFIRMED,
    MATCH_MISSING,
    MATCH_NEED_REVIEW,
    NEW_LISTING_DAYS,
    PLATFORM_SHOPEE,
    PLATFORM_TIKTOK,
    PRICE_BAND_GREEN,
    PRICE_BAND_RED,
    PRICE_BAND_YELLOW,
    PRICE_GAP_GREEN_MAX,
    PRICE_GAP_YELLOW_MAX,
    TOP_PRODUCTS_FOR_PRICE_GAP,
)
from seller.assortment.db import get_session
from seller.assortment.models import CompetitorProduct, ProductMatch, TrackerFetchStatus
from seller.assortment.shop_context import get_shop_meta_map, product_to_dict, shop_header


def _parse_sku_display(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
    except json.JSONDecodeError:
        pass
    return [raw]


def competitor_data_available(session=None) -> bool:
    if session is not None:
        return session.query(CompetitorProduct).count() > 0
    session = get_session()
    try:
        return session.query(CompetitorProduct).count() > 0
    finally:
        session.close()


def _data_meta(session) -> dict[str, Any]:
    has = competitor_data_available(session)
    return {
        "has_competitor_data": has,
        "empty_message": None if has else "No competitor data available",
    }


def _price_gap_band(gap_pct: float | None) -> str | None:
    if gap_pct is None:
        return None
    abs_gap = abs(gap_pct)
    if abs_gap <= PRICE_GAP_GREEN_MAX:
        return PRICE_BAND_GREEN
    if abs_gap <= PRICE_GAP_YELLOW_MAX:
        return PRICE_BAND_YELLOW
    return PRICE_BAND_RED


def _avg_price(products: list[CompetitorProduct], limit: int = TOP_PRODUCTS_FOR_PRICE_GAP) -> float | None:
    prices = [p.price for p in products[:limit] if p.price is not None]
    if not prices:
        return None
    return round(sum(prices) / len(prices), 2)


def _shop_price_gap_pct(shopee_avg: float | None, tiktok_avg: float | None) -> float | None:
    if shopee_avg is None or tiktok_avg is None or shopee_avg == 0:
        return None
    return round(((tiktok_avg - shopee_avg) / shopee_avg) * 100, 2)


def _is_confirmed(match: ProductMatch) -> bool:
    return match.match_status == MATCH_CONFIRMED or match.human_confirmed


def _listed_within_days(p: CompetitorProduct, days: int = NEW_LISTING_DAYS) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    ref = p.listed_at or p.first_detected_at
    if not ref:
        return False
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return ref >= cutoff


def _group_by_shop(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for item in items:
        sid = item.get("seller_id") or "unknown"
        if sid not in groups:
            groups[sid] = {
                **shop_header(sid),
                "items": [],
            }
        groups[sid]["items"].append(item)
    return sorted(groups.values(), key=lambda g: str(g.get("row_number") or g.get("seller_name") or ""))


def get_dashboard_metrics() -> dict[str, Any]:
    session = get_session()
    try:
        meta = _data_meta(session)
        shopee_count = (
            session.query(CompetitorProduct).filter(CompetitorProduct.platform == PLATFORM_SHOPEE).count()
        )
        tiktok_count = (
            session.query(CompetitorProduct).filter(CompetitorProduct.platform == PLATFORM_TIKTOK).count()
        )

        matches = session.query(ProductMatch).all()
        confirmed = sum(1 for m in matches if _is_confirmed(m))
        need_review = sum(
            1 for m in matches if m.match_status == MATCH_NEED_REVIEW and not m.human_confirmed
        )
        missing = sum(1 for m in matches if m.match_status == MATCH_MISSING)

        higher = lower = 0
        for m in matches:
            if not _is_confirmed(m) or not m.shopee_product_id or not m.tiktok_product_id:
                continue
            shopee = session.get(CompetitorProduct, m.shopee_product_id)
            tiktok = session.get(CompetitorProduct, m.tiktok_product_id)
            if not shopee or not tiktok or shopee.price is None or tiktok.price is None:
                continue
            if shopee.price > tiktok.price:
                higher += 1
            elif shopee.price < tiktok.price:
                lower += 1

        new_recent = 0
        for m in matches:
            if m.match_status != MATCH_MISSING:
                continue
            tiktok = session.get(CompetitorProduct, m.tiktok_product_id) if m.tiktok_product_id else None
            if tiktok and _listed_within_days(tiktok):
                new_recent += 1

        return {
            **meta,
            "total_products_compared": shopee_count + tiktok_count,
            "matched_products": confirmed,
            "missing_products": missing,
            "need_review_products": need_review,
            "higher_priced_products": higher,
            "lower_priced_products": lower,
            "new_listings_recent": new_recent,
            "new_listings_today": new_recent,
        }
    finally:
        session.close()


def list_missing_assortment() -> dict[str, Any]:
    session = get_session()
    try:
        meta = _data_meta(session)
        if not meta["has_competitor_data"]:
            return {**meta, "groups": []}
        rows = (
            session.query(ProductMatch, CompetitorProduct)
            .join(CompetitorProduct, ProductMatch.tiktok_product_id == CompetitorProduct.id)
            .filter(ProductMatch.match_status == MATCH_MISSING)
            .order_by(ProductMatch.similarity_score.desc())
            .all()
        )
        items = []
        for match, tiktok in rows:
            sid = tiktok.competitor_shop_id or ""
            hdr = shop_header(sid)
            reason = (
                f"Best Shopee similarity {match.similarity_score}% — below missing threshold"
                if match.similarity_score
                else "Not found in Shopee assortment"
            )
            items.append(
                {
                    "seller_id": sid,
                    "seller_name": hdr["seller_name"],
                    "shopee_link": hdr["shopee_link"],
                    "tiktok_link": hdr["tiktok_link"],
                    "match_id": match.id,
                    "product_image_url": tiktok.product_image_url,
                    "product_name": tiktok.product_name,
                    "product_link": tiktok.product_link,
                    "sku_variations": _parse_sku_display(tiktok.sku_variations),
                    "confidence_score": match.similarity_score,
                    "reason": reason,
                }
            )
        return {**meta, "groups": _group_by_shop(items)}
    finally:
        session.close()


def list_need_review() -> dict[str, Any]:
    session = get_session()
    try:
        meta = _data_meta(session)
        if not meta["has_competitor_data"]:
            return {**meta, "groups": []}
        rows = (
            session.query(ProductMatch)
            .filter(
                ProductMatch.match_status == MATCH_NEED_REVIEW,
                ProductMatch.human_confirmed.is_(False),
            )
            .order_by(ProductMatch.similarity_score.desc())
            .all()
        )
        items = []
        for match in rows:
            tiktok = session.get(CompetitorProduct, match.tiktok_product_id) if match.tiktok_product_id else None
            shopee = session.get(CompetitorProduct, match.shopee_product_id) if match.shopee_product_id else None
            if not tiktok:
                continue
            sid = tiktok.competitor_shop_id or match.competitor_shop_id or ""
            hdr = shop_header(sid)
            items.append(
                {
                    "seller_id": sid,
                    "seller_name": hdr["seller_name"],
                    "shopee_link": hdr["shopee_link"],
                    "tiktok_link": hdr["tiktok_link"],
                    "match_id": match.id,
                    "similarity_score": match.similarity_score,
                    "image_similarity": match.image_similarity,
                    "title_similarity": match.title_similarity,
                    "sku_similarity": match.sku_similarity,
                    "reason": "Possible match — review recommended",
                    "shopee": product_to_dict(shopee) if shopee else None,
                    "tiktok": product_to_dict(tiktok),
                    "sku_comparison": {
                        "shopee": _parse_sku_display(shopee.sku_variations) if shopee else [],
                        "tiktok": _parse_sku_display(tiktok.sku_variations),
                    },
                }
            )
        return {**meta, "groups": _group_by_shop(items)}
    finally:
        session.close()


def list_price_gap_analysis() -> dict[str, Any]:
    session = get_session()
    try:
        meta = _data_meta(session)
        meta_map = get_shop_meta_map()
        shop_ids = set(meta_map.keys())
        shop_ids.update(
            row[0]
            for row in session.query(CompetitorProduct.competitor_shop_id).distinct().all()
            if row[0]
        )

        items = []
        for shop_id in sorted(shop_ids, key=str):
            hdr = shop_header(shop_id, meta_map)
            shopee_products = (
                session.query(CompetitorProduct)
                .filter(
                    CompetitorProduct.competitor_shop_id == shop_id,
                    CompetitorProduct.platform == PLATFORM_SHOPEE,
                )
                .order_by(CompetitorProduct.id)
                .all()
            )
            tiktok_products = (
                session.query(CompetitorProduct)
                .filter(
                    CompetitorProduct.competitor_shop_id == shop_id,
                    CompetitorProduct.platform == PLATFORM_TIKTOK,
                )
                .order_by(CompetitorProduct.id)
                .all()
            )

            shopee_avg = _avg_price(shopee_products)
            tiktok_avg = _avg_price(tiktok_products)
            gap = _shop_price_gap_pct(shopee_avg, tiktok_avg)

            status_row = session.query(TrackerFetchStatus).filter(
                TrackerFetchStatus.seller_id == shop_id
            ).first()
            shopee_na_reason = None
            tiktok_na_reason = None
            if status_row and status_row.link_results_json:
                try:
                    stored = json.loads(status_row.link_results_json)
                    if isinstance(stored, dict):
                        shopee_na_reason = stored.get("shopee_reason")
                        tiktok_na_reason = stored.get("tiktok_reason")
                except json.JSONDecodeError:
                    pass

            reason_parts = []
            if shopee_avg is None:
                reason_parts.append(shopee_na_reason or "Shopee average price unavailable")
            if tiktok_avg is None:
                reason_parts.append(tiktok_na_reason or "TikTok top 10 average price unavailable")

            items.append(
                {
                    "seller_id": shop_id,
                    "seller_name": hdr["seller_name"],
                    "shopee_link": hdr["shopee_link"],
                    "tiktok_link": hdr["tiktok_link"],
                    "shopee_avg_price": shopee_avg,
                    "tiktok_top10_avg_price": tiktok_avg,
                    "price_gap_pct": gap,
                    "price_gap_band": _price_gap_band(gap),
                    "status": _price_gap_band(gap) or ("na" if reason_parts else None),
                    "reason": "; ".join(reason_parts) if reason_parts else None,
                }
            )

        items.sort(key=lambda x: abs(x.get("price_gap_pct") or 0), reverse=True)
        return {**meta, "items": items}
    finally:
        session.close()


def list_new_listing_alerts() -> dict[str, Any]:
    session = get_session()
    try:
        meta = _data_meta(session)
        if not meta["has_competitor_data"]:
            return {**meta, "groups": []}

        rows = (
            session.query(ProductMatch, CompetitorProduct)
            .join(CompetitorProduct, ProductMatch.tiktok_product_id == CompetitorProduct.id)
            .filter(ProductMatch.match_status == MATCH_MISSING)
            .all()
        )
        items = []
        for match, tiktok in rows:
            if not _listed_within_days(tiktok):
                continue
            sid = tiktok.competitor_shop_id or ""
            hdr = shop_header(sid)
            listed = tiktok.listed_at or tiktok.first_detected_at
            items.append(
                {
                    "seller_id": sid,
                    "seller_name": hdr["seller_name"],
                    "shopee_link": hdr["shopee_link"],
                    "tiktok_link": hdr["tiktok_link"],
                    "competitor_product_id": tiktok.id,
                    "product_image_url": tiktok.product_image_url,
                    "product_name": tiktok.product_name,
                    "product_link": tiktok.product_link,
                    "listed_at": listed.isoformat() if listed else None,
                    "first_detected_at": tiktok.first_detected_at.isoformat()
                    if tiktok.first_detected_at
                    else None,
                    "reason": "Not found in Shopee assortment",
                }
            )
        items.sort(key=lambda x: x.get("listed_at") or "", reverse=True)
        return {**meta, "groups": _group_by_shop(items)}
    finally:
        session.close()


def confirm_match(match_id: int) -> dict[str, Any]:
    session = get_session()
    try:
        row = session.get(ProductMatch, match_id)
        if not row:
            return {"ok": False, "error": "not_found"}
        row.human_confirmed = True
        row.human_reviewed = True
        row.match_status = MATCH_CONFIRMED
        session.commit()
        return {"ok": True, "match_id": match_id, "status": MATCH_CONFIRMED}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dismiss_new_listing(competitor_product_id: int) -> dict[str, Any]:
    session = get_session()
    try:
        row = session.get(CompetitorProduct, competitor_product_id)
        if not row:
            return {"ok": False, "error": "not_found"}
        row.is_new_listing = False
        if row.listed_at:
            row.listed_at = datetime.now(timezone.utc) - timedelta(days=NEW_LISTING_DAYS + 1)
        session.commit()
        return {"ok": True}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
