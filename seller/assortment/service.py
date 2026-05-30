from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from seller.assortment.constants import (
    MATCH_CONFIRMED,
    MATCH_MISSING,
    MATCH_NEED_REVIEW,
    PRICE_BAND_GREEN,
    PRICE_BAND_RED,
    PRICE_BAND_YELLOW,
    PRICE_GAP_GREEN_MAX,
    PRICE_GAP_YELLOW_MAX,
)
from seller.assortment.db import get_session
from seller.assortment.models import CompetitorProduct, OurProduct, ProductMatch


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


def _product_dict(p, *, prefix: str = "") -> dict[str, Any]:
    return {
        f"{prefix}id": p.id,
        f"{prefix}product_name": p.product_name,
        f"{prefix}product_link": p.product_link,
        f"{prefix}product_image_url": p.product_image_url,
        f"{prefix}sku_variations": _parse_sku_display(p.sku_variations),
        f"{prefix}price": p.price,
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


def _price_gap_pct(our_price: float | None, comp_price: float | None) -> float | None:
    if our_price is None or comp_price is None or our_price == 0:
        return None
    return round(((comp_price - our_price) / our_price) * 100, 2)


def get_dashboard_metrics() -> dict[str, Any]:
    session = get_session()
    try:
        meta = _data_meta(session)
        total_comp = session.query(CompetitorProduct).count()
        matches = session.query(ProductMatch).all()
        confirmed = sum(
            1 for m in matches if m.match_status == MATCH_CONFIRMED or m.human_confirmed
        )
        need_review = sum(1 for m in matches if m.match_status == MATCH_NEED_REVIEW and not m.human_confirmed)
        missing = sum(1 for m in matches if m.match_status == MATCH_MISSING)

        today = datetime.now(timezone.utc).date()
        new_today = (
            session.query(CompetitorProduct)
            .filter(CompetitorProduct.is_new_listing.is_(True))
            .count()
        )

        higher = lower = 0
        price_rows = (
            session.query(ProductMatch, OurProduct, CompetitorProduct)
            .join(OurProduct, ProductMatch.our_product_id == OurProduct.id)
            .join(CompetitorProduct, ProductMatch.competitor_product_id == CompetitorProduct.id)
            .filter(
                (ProductMatch.match_status == MATCH_CONFIRMED) | (ProductMatch.human_confirmed.is_(True))
            )
            .all()
        )
        for _m, our, comp in price_rows:
            gap = _price_gap_pct(our.price, comp.price)
            if gap is None:
                continue
            if gap > PRICE_GAP_GREEN_MAX:
                higher += 1
            elif gap < -PRICE_GAP_GREEN_MAX:
                lower += 1

        return {
            **meta,
            "total_products_compared": total_comp,
            "matched_products": confirmed,
            "missing_products": missing,
            "need_review_products": need_review,
            "higher_priced_products": higher,
            "lower_priced_products": lower,
            "new_listings_today": new_today,
        }
    finally:
        session.close()


def list_missing_assortment() -> dict[str, Any]:
    session = get_session()
    try:
        meta = _data_meta(session)
        if not meta["has_competitor_data"]:
            return {**meta, "items": []}
        rows = (
            session.query(ProductMatch, CompetitorProduct)
            .join(CompetitorProduct, ProductMatch.competitor_product_id == CompetitorProduct.id)
            .filter(ProductMatch.match_status == MATCH_MISSING)
            .order_by(ProductMatch.similarity_score.desc())
            .all()
        )
        out = []
        for match, comp in rows:
            out.append(
                {
                    "match_id": match.id,
                    "product_image_url": comp.product_image_url,
                    "product_name": comp.product_name,
                    "product_link": comp.product_link,
                    "sku_variations": _parse_sku_display(comp.sku_variations),
                    "confidence_score": match.similarity_score,
                    "image_similarity": match.image_similarity,
                    "title_similarity": match.title_similarity,
                    "sku_similarity": match.sku_similarity,
                }
            )
        return {**meta, "items": out}
    finally:
        session.close()


def list_need_review() -> dict[str, Any]:
    session = get_session()
    try:
        meta = _data_meta(session)
        if not meta["has_competitor_data"]:
            return {**meta, "items": []}
        rows = (
            session.query(ProductMatch, CompetitorProduct, OurProduct)
            .join(CompetitorProduct, ProductMatch.competitor_product_id == CompetitorProduct.id)
            .outerjoin(OurProduct, ProductMatch.our_product_id == OurProduct.id)
            .filter(
                ProductMatch.match_status == MATCH_NEED_REVIEW,
                ProductMatch.human_confirmed.is_(False),
            )
            .order_by(ProductMatch.similarity_score.desc())
            .all()
        )
        out = []
        for match, comp, our in rows:
            item = {
                "match_id": match.id,
                "similarity_score": match.similarity_score,
                "image_similarity": match.image_similarity,
                "title_similarity": match.title_similarity,
                "sku_similarity": match.sku_similarity,
                "competitor": {
                    "product_image_url": comp.product_image_url,
                    "product_name": comp.product_name,
                    "product_link": comp.product_link,
                    "sku_variations": _parse_sku_display(comp.sku_variations),
                },
                "our": None,
                "sku_comparison": {
                    "our": [],
                    "competitor": _parse_sku_display(comp.sku_variations),
                },
            }
            if our:
                item["our"] = {
                    "product_image_url": our.product_image_url,
                    "product_name": our.product_name,
                    "product_link": our.product_link,
                    "sku_variations": _parse_sku_display(our.sku_variations),
                }
                item["sku_comparison"]["our"] = _parse_sku_display(our.sku_variations)
            out.append(item)
        return {**meta, "items": out}
    finally:
        session.close()


def list_price_gap_analysis() -> dict[str, Any]:
    session = get_session()
    try:
        meta = _data_meta(session)
        if not meta["has_competitor_data"]:
            return {**meta, "items": []}
        rows = (
            session.query(ProductMatch, CompetitorProduct, OurProduct)
            .join(CompetitorProduct, ProductMatch.competitor_product_id == CompetitorProduct.id)
            .join(OurProduct, ProductMatch.our_product_id == OurProduct.id)
            .filter(
                (ProductMatch.match_status == MATCH_CONFIRMED) | (ProductMatch.human_confirmed.is_(True))
            )
            .all()
        )
        out = []
        for match, comp, our in rows:
            gap = _price_gap_pct(our.price, comp.price)
            out.append(
                {
                    "match_id": match.id,
                    "product_name": our.product_name,
                    "our_price": our.price,
                    "competitor_price": comp.price,
                    "price_gap_pct": gap,
                    "price_gap_band": _price_gap_band(gap),
                }
            )
        out.sort(key=lambda x: abs(x["price_gap_pct"] or 0), reverse=True)
        return {**meta, "items": out}
    finally:
        session.close()


def list_new_listing_alerts() -> dict[str, Any]:
    session = get_session()
    try:
        meta = _data_meta(session)
        if not meta["has_competitor_data"]:
            return {**meta, "items": []}
        rows = (
            session.query(CompetitorProduct)
            .filter(CompetitorProduct.is_new_listing.is_(True))
            .order_by(CompetitorProduct.first_detected_at.desc())
            .all()
        )
        items = [
            {
                "competitor_product_id": p.id,
                "product_image_url": p.product_image_url,
                "product_name": p.product_name,
                "product_link": p.product_link,
                "first_detected_at": p.first_detected_at.isoformat() if p.first_detected_at else None,
            }
            for p in rows
        ]
        return {**meta, "items": items}
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
        session.commit()
        return {"ok": True}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
