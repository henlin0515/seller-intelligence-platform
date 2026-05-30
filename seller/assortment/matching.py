from __future__ import annotations

import logging
from typing import Any

from seller.assortment.constants import (
    MATCH_CONFIRMED,
    MATCH_MISSING,
    MATCH_NEED_REVIEW,
    PLATFORM_SHOPEE,
    PLATFORM_TIKTOK,
    THRESHOLD_CONFIRMED,
    THRESHOLD_NEED_REVIEW,
    WEIGHT_IMAGE,
    WEIGHT_SKU,
    WEIGHT_TITLE,
)
from seller.assortment.db import get_session
from seller.assortment.models import CompetitorProduct, ProductMatch
from seller.assortment.similarity import image_similarity, sku_similarity, title_similarity

logger = logging.getLogger("seller.assortment.matching")


def classify_score(score: float) -> str:
    if score >= THRESHOLD_CONFIRMED:
        return MATCH_CONFIRMED
    if score >= THRESHOLD_NEED_REVIEW:
        return MATCH_NEED_REVIEW
    return MATCH_MISSING


def compute_similarity_between(
    shopee: CompetitorProduct,
    tiktok: CompetitorProduct,
    *,
    image_provider: Any | None = None,
) -> dict[str, float]:
    img = image_similarity(
        shopee.product_image_url,
        tiktok.product_image_url,
        provider=image_provider,
    )
    title = title_similarity(shopee.product_name, tiktok.product_name)
    sku = sku_similarity(shopee.sku_variations, tiktok.sku_variations)
    total = round(img * WEIGHT_IMAGE + title * WEIGHT_TITLE + sku * WEIGHT_SKU, 2)
    return {
        "image_similarity": img,
        "title_similarity": title,
        "sku_similarity": sku,
        "similarity_score": total,
    }


def run_matching_for_shop(
    session,
    shop_id: str,
    *,
    image_provider: Any | None = None,
) -> int:
    """Match each TikTok product to best Shopee product within the same shop pair."""
    shopee_products = (
        session.query(CompetitorProduct)
        .filter(
            CompetitorProduct.competitor_shop_id == shop_id,
            CompetitorProduct.platform == PLATFORM_SHOPEE,
        )
        .all()
    )
    tiktok_products = (
        session.query(CompetitorProduct)
        .filter(
            CompetitorProduct.competitor_shop_id == shop_id,
            CompetitorProduct.platform == PLATFORM_TIKTOK,
        )
        .all()
    )

    session.query(ProductMatch).filter(ProductMatch.competitor_shop_id == shop_id).delete()

    written = 0
    for tiktok in tiktok_products:
        best: dict[str, float] | None = None
        best_shopee: CompetitorProduct | None = None

        for shopee in shopee_products:
            scores = compute_similarity_between(shopee, tiktok, image_provider=image_provider)
            if best is None or scores["similarity_score"] > best["similarity_score"]:
                best = scores
                best_shopee = shopee

        if best is None:
            best = {
                "image_similarity": 0.0,
                "title_similarity": 0.0,
                "sku_similarity": 0.0,
                "similarity_score": 0.0,
            }

        status = classify_score(best["similarity_score"])
        row = ProductMatch(
            competitor_shop_id=shop_id,
            tiktok_product_id=tiktok.id,
            competitor_product_id=tiktok.id,
            shopee_product_id=best_shopee.id if best_shopee else None,
            image_similarity=best["image_similarity"],
            title_similarity=best["title_similarity"],
            sku_similarity=best["sku_similarity"],
            similarity_score=best["similarity_score"],
            match_status=status,
        )
        session.add(row)
        written += 1

    return written


def run_matching_for_all_competitors(*, image_provider: Any | None = None) -> dict[str, int]:
    session = get_session()
    stats = {"shop_pairs": 0, "matches_written": 0, "tiktok_products": 0}
    try:
        shop_ids = [
            row[0]
            for row in session.query(CompetitorProduct.competitor_shop_id)
            .filter(CompetitorProduct.competitor_shop_id.isnot(None))
            .distinct()
            .all()
            if row[0]
        ]
        stats["shop_pairs"] = len(shop_ids)
        stats["tiktok_products"] = (
            session.query(CompetitorProduct)
            .filter(CompetitorProduct.platform == PLATFORM_TIKTOK)
            .count()
        )
        for shop_id in shop_ids:
            stats["matches_written"] += run_matching_for_shop(
                session, shop_id, image_provider=image_provider
            )
        session.commit()
        return stats
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
