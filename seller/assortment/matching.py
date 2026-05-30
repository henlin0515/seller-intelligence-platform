from __future__ import annotations

import logging
from typing import Any

from seller.assortment.constants import (
    MATCH_CONFIRMED,
    MATCH_MISSING,
    MATCH_NEED_REVIEW,
    THRESHOLD_CONFIRMED,
    THRESHOLD_NEED_REVIEW,
    WEIGHT_IMAGE,
    WEIGHT_SKU,
    WEIGHT_TITLE,
)
from seller.assortment.db import get_session
from seller.assortment.models import CompetitorProduct, OurProduct, ProductMatch
from seller.assortment.similarity import image_similarity, sku_similarity, title_similarity

logger = logging.getLogger("seller.assortment.matching")


def classify_score(score: float) -> str:
    if score >= THRESHOLD_CONFIRMED:
        return MATCH_CONFIRMED
    if score >= THRESHOLD_NEED_REVIEW:
        return MATCH_NEED_REVIEW
    return MATCH_MISSING


def compute_similarity_score(
    our: OurProduct,
    comp: CompetitorProduct,
    *,
    image_provider: Any | None = None,
) -> dict[str, float]:
    img = image_similarity(
        our.product_image_url,
        comp.product_image_url,
        provider=image_provider,
    )
    title = title_similarity(our.product_name, comp.product_name)
    sku = sku_similarity(our.sku_variations, comp.sku_variations)
    total = round(img * WEIGHT_IMAGE + title * WEIGHT_TITLE + sku * WEIGHT_SKU, 2)
    return {
        "image_similarity": img,
        "title_similarity": title,
        "sku_similarity": sku,
        "similarity_score": total,
    }


def run_matching_for_all_competitors(*, image_provider: Any | None = None) -> dict[str, int]:
    """
    For each competitor product, find best our-product match and persist ProductMatch row.
    Price is NOT used in matching.
    """
    session = get_session()
    stats = {"competitor_products": 0, "matches_written": 0}
    try:
        our_products = session.query(OurProduct).all()
        competitors = session.query(CompetitorProduct).all()
        stats["competitor_products"] = len(competitors)

        for comp in competitors:
            best: dict[str, Any] | None = None
            best_our: OurProduct | None = None

            for our in our_products:
                scores = compute_similarity_score(our, comp, image_provider=image_provider)
                if best is None or scores["similarity_score"] > best["similarity_score"]:
                    best = scores
                    best_our = our

            if best is None:
                best = {
                    "image_similarity": 0.0,
                    "title_similarity": 0.0,
                    "sku_similarity": 0.0,
                    "similarity_score": 0.0,
                }

            status = classify_score(best["similarity_score"])
            existing = (
                session.query(ProductMatch)
                .filter(ProductMatch.competitor_product_id == comp.id)
                .order_by(ProductMatch.id.desc())
                .first()
            )
            if existing:
                row = existing
            else:
                row = ProductMatch(competitor_product_id=comp.id)
                session.add(row)

            row.our_product_id = best_our.id if best_our else None
            row.image_similarity = best["image_similarity"]
            row.title_similarity = best["title_similarity"]
            row.sku_similarity = best["sku_similarity"]
            row.similarity_score = best["similarity_score"]
            if row.human_confirmed:
                row.match_status = MATCH_CONFIRMED
            else:
                row.match_status = status
            stats["matches_written"] += 1

        session.commit()
        return stats
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
