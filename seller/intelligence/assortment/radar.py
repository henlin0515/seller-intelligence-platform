"""TikTok Product Radar — FastMoss-only assortment intelligence."""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, date, datetime
from typing import Any

from seller.fastmoss.goods import GOODS_PATH, fetch_shop_goods_catalog
from seller.fastmoss.mapping import MAPPING_MAPPED, load_fastmoss_mapping
from seller.fastmoss.recent_data import _base_url

logger = logging.getLogger("seller.intelligence.assortment.radar")

NEW_PRODUCT_DAYS = int(os.getenv("ASSORTMENT_NEW_PRODUCT_DAYS", "20"))
RADAR_MAX_PRODUCTS = int(
    os.getenv("ASSORTMENT_RADAR_MAX_PRODUCTS", os.getenv("FASTMOSS_MAX_PRODUCTS", "1000"))
)
RADAR_PAGE_SIZE = int(
    os.getenv("ASSORTMENT_RADAR_PAGE_SIZE", os.getenv("FASTMOSS_PAGE_SIZE", "10"))
)
RADAR_TOP_GROWTH = int(os.getenv("ASSORTMENT_RADAR_TOP_GROWTH", "20"))
RADAR_TOP_NEW = int(os.getenv("ASSORTMENT_RADAR_TOP_NEW", "20"))
RADAR_TOP_OPPORTUNITIES = int(os.getenv("ASSORTMENT_RADAR_TOP_OPPORTUNITIES", "20"))
RADAR_CACHE_SEC = int(os.getenv("ASSORTMENT_RADAR_CACHE_SEC", "900"))

_cache_payload: dict[str, Any] | None = None
_cache_ts: float = 0.0


def _parse_upload_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt, size in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:size], fmt).date()
        except ValueError:
            continue
    return None


def days_since_launch(upload_date: str | None, *, today: date | None = None) -> int | None:
    parsed = _parse_upload_date(upload_date)
    if not parsed:
        return None
    ref = today or date.today()
    return max(0, (ref - parsed).days)


def new_product_badge(days: int | None) -> str | None:
    if days is None or days > NEW_PRODUCT_DAYS:
        return None
    if days <= 3:
        return "3 DAYS"
    if days <= 7:
        return "7 DAYS"
    if days <= 14:
        return "14 DAYS"
    return "20 DAYS"


def _percentile_rank(values: list[float], target: float, *, higher_is_better: bool = True) -> float:
    if not values:
        return 0.0
    if higher_is_better:
        below = sum(1 for v in values if v < target)
    else:
        below = sum(1 for v in values if v > target)
    return round((below / len(values)) * 100, 2)


def _normalize_scores(raw_scores: list[float]) -> list[float]:
    if not raw_scores:
        return []
    lo = min(raw_scores)
    hi = max(raw_scores)
    if hi <= lo:
        return [50.0 for _ in raw_scores]
    return [round(((v - lo) / (hi - lo)) * 100, 2) for v in raw_scores]


def compute_growth_raw(product: dict[str, Any]) -> float:
    days = max(product.get("days_since_launch") or 30, 1)
    sales_amount = float(product.get("sales_amount") or 0)
    sold_count = float(product.get("sold_count") or 0)
    sales_velocity = sales_amount / days
    sold_velocity = sold_count / days
    engagement = (
        float(product.get("relate_video_count") or 0) * 1.0
        + float(product.get("relate_live_count") or 0) * 1.2
        + float(product.get("relate_author_count") or 0) * 0.5
    )
    inc_boost = float(product.get("inc_sold_count") or 0) * 10.0
    inc_sales_boost = float(product.get("inc_sale_amount") or 0) * 0.001
    return (
        sales_velocity * 0.35
        + sold_velocity * 0.25
        + engagement * 0.20
        + sales_amount * 0.0000015
        + inc_boost
        + inc_sales_boost
    )


def enrich_product_metrics(products: list[dict[str, Any]], *, today: date | None = None) -> list[dict[str, Any]]:
    ref = today or date.today()
    enriched: list[dict[str, Any]] = []
    for row in products:
        days = days_since_launch(row.get("upload_date") or row.get("listed_date"), today=ref)
        item = {
            **row,
            "days_since_launch": days,
            "is_new_product": days is not None and days <= NEW_PRODUCT_DAYS,
            "new_badge": new_product_badge(days),
        }
        enriched.append(item)

    raw_growth = [compute_growth_raw(p) for p in enriched]
    growth_scores = _normalize_scores(raw_growth)
    sales_values = [float(p.get("sales_amount") or 0) for p in enriched]
    growth_values = growth_scores
    newness_values = [
        float(NEW_PRODUCT_DAYS - (p.get("days_since_launch") or NEW_PRODUCT_DAYS + 1))
        if p.get("is_new_product")
        else 0.0
        for p in enriched
    ]

    for idx, product in enumerate(enriched):
        sales_rank = _percentile_rank(sales_values, float(product.get("sales_amount") or 0))
        growth_rank = _percentile_rank(growth_values, growth_scores[idx])
        newness_rank = _percentile_rank(newness_values, newness_values[idx])
        opportunity_score = round(
            0.5 * sales_rank + 0.3 * growth_rank + 0.2 * newness_rank,
            2,
        )
        product["growth_score"] = growth_scores[idx]
        product["growth_raw"] = raw_growth[idx]
        product["sales_rank"] = sales_rank
        product["growth_rank"] = growth_rank
        product["newness_rank"] = newness_rank
        product["opportunity_score"] = opportunity_score
        product["opportunity_label"] = "HIGH OPPORTUNITY" if opportunity_score >= 60 else None
        product["trend_arrow"] = "up" if growth_scores[idx] >= 55 else "flat"
    return enriched


def _sort_key_sales(product: dict[str, Any]) -> tuple[float, float]:
    return (float(product.get("sales_amount") or 0), float(product.get("sold_count") or 0))


def _uncategorized(category: str | None) -> str:
    text = str(category or "").strip()
    return text or "Uncategorized"


def _shop_sales_totals(products: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for row in products:
        shop_id = str(row.get("seller_shop_id") or "").strip()
        if not shop_id:
            continue
        bucket = totals.setdefault(
            shop_id,
            {
                "shop_id": shop_id,
                "shop_name": row.get("seller_shop_name") or row.get("shop_name") or shop_id,
                "total_sales_amount": 0.0,
                "total_sold_count": 0.0,
                "product_count": 0,
            },
        )
        bucket["total_sales_amount"] += float(row.get("sales_amount") or 0)
        bucket["total_sold_count"] += float(row.get("sold_count") or 0)
        bucket["product_count"] += 1
    return totals


def _build_shop_view(enriched: list[dict[str, Any]]) -> dict[str, Any]:
    by_shop: dict[str, list[dict[str, Any]]] = {}
    shop_names: dict[str, str] = {}
    for row in enriched:
        shop_id = str(row.get("seller_shop_id") or "").strip()
        if not shop_id:
            continue
        by_shop.setdefault(shop_id, []).append(row)
        shop_names[shop_id] = row.get("seller_shop_name") or row.get("shop_name") or shop_id

    shops: list[dict[str, Any]] = []
    for shop_id in sorted(shop_names, key=lambda sid: shop_names[sid].lower()):
        products = by_shop.get(shop_id) or []
        top_products = sorted(products, key=_sort_key_sales, reverse=True)
        new_products = sorted(
            [p for p in products if p.get("is_new_product")],
            key=_sort_key_sales,
            reverse=True,
        )
        growth_products = sorted(
            products,
            key=lambda p: float(p.get("growth_score") or 0),
            reverse=True,
        )[:RADAR_TOP_GROWTH]
        opportunity_products = sorted(
            products,
            key=lambda p: float(p.get("opportunity_score") or 0),
            reverse=True,
        )[:RADAR_TOP_OPPORTUNITIES]

        shops.append(
            {
                "shop_id": shop_id,
                "shop_name": shop_names[shop_id],
                "summary": {
                    "total_products": len(products),
                    "new_products_20d": len(new_products),
                    "growth_products": len(growth_products),
                    "opportunity_products": len(opportunity_products),
                },
                "top_products": [
                    _public_product(p, rank=i + 1) for i, p in enumerate(top_products)
                ],
                "new_products": [
                    _public_product(p, rank=i + 1) for i, p in enumerate(new_products)
                ],
                "growth_products": [
                    _public_product(p, rank=i + 1) for i, p in enumerate(growth_products)
                ],
                "opportunity_products": [
                    _public_product(p, rank=i + 1) for i, p in enumerate(opportunity_products)
                ],
            }
        )
    return {"shops": shops}


def _build_category_dashboard(enriched: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, list[dict[str, Any]]] = {}
    for row in enriched:
        category = _uncategorized(row.get("category"))
        by_category.setdefault(category, []).append(row)

    summaries: list[dict[str, Any]] = []
    details: dict[str, dict[str, Any]] = {}

    for category in sorted(by_category, key=str.lower):
        products = by_category[category]
        total_sales = sum(float(p.get("sales_amount") or 0) for p in products)
        total_sold = sum(float(p.get("sold_count") or 0) for p in products)
        new_products = sorted(
            [p for p in products if p.get("is_new_product")],
            key=_sort_key_sales,
            reverse=True,
        )
        growth_products = sorted(
            products,
            key=lambda p: float(p.get("growth_score") or 0),
            reverse=True,
        )[:RADAR_TOP_GROWTH]
        top_products = sorted(products, key=_sort_key_sales, reverse=True)

        shop_totals = _shop_sales_totals(products)
        top_shop_row = max(
            shop_totals.values(),
            key=lambda row: float(row.get("total_sales_amount") or 0),
            default=None,
        )
        top_product_row = top_products[0] if top_products else None
        top_shops = sorted(
            shop_totals.values(),
            key=lambda row: float(row.get("total_sales_amount") or 0),
            reverse=True,
        )

        summaries.append(
            {
                "category": category,
                "total_products": len(products),
                "total_sales_amount": round(total_sales, 2),
                "total_sold_count": int(total_sold),
                "new_products_20d": len(new_products),
                "growth_products": len(growth_products),
                "top_shop": {
                    "shop_id": top_shop_row.get("shop_id") if top_shop_row else None,
                    "shop_name": top_shop_row.get("shop_name") if top_shop_row else None,
                    "total_sales_amount": top_shop_row.get("total_sales_amount") if top_shop_row else None,
                }
                if top_shop_row
                else None,
                "top_product": {
                    "product_id": top_product_row.get("product_id"),
                    "product_name": top_product_row.get("product_name"),
                    "product_image": top_product_row.get("product_image"),
                    "sales_amount": top_product_row.get("sales_amount"),
                    "sold_count": top_product_row.get("sold_count"),
                }
                if top_product_row
                else None,
            }
        )

        details[category] = {
            "top_products": [
                _public_product(p, rank=i + 1) for i, p in enumerate(top_products[:100])
            ],
            "new_products": [
                _public_product(p, rank=i + 1) for i, p in enumerate(new_products)
            ],
            "growth_products": [
                _public_product(p, rank=i + 1) for i, p in enumerate(growth_products)
            ],
            "top_shops": [
                {
                    "rank": i + 1,
                    "shop_id": row.get("shop_id"),
                    "shop_name": row.get("shop_name"),
                    "total_sales_amount": row.get("total_sales_amount"),
                    "total_sold_count": row.get("total_sold_count"),
                    "product_count": row.get("product_count"),
                }
                for i, row in enumerate(top_shops)
            ],
        }

    return {"categories": summaries, "category_details": details}


def _public_product(row: dict[str, Any], *, rank: int | None = None) -> dict[str, Any]:
    out = {
        "rank": rank,
        "product_id": row.get("product_id"),
        "product_name": row.get("product_name"),
        "product_image": row.get("product_image"),
        "category": row.get("category"),
        "product_price_php": row.get("product_price_php"),
        "sold_count": row.get("sold_count"),
        "sales_amount": row.get("sales_amount"),
        "upload_date": row.get("upload_date") or row.get("listed_date"),
        "days_since_launch": row.get("days_since_launch"),
        "shop_name": row.get("seller_shop_name") or row.get("shop_name"),
        "seller_shop_id": row.get("seller_shop_id"),
        "fastmoss_shop_id": row.get("fastmoss_shop_id"),
        "product_link": row.get("product_link"),
        "new_badge": row.get("new_badge"),
        "is_new_product": row.get("is_new_product"),
        "growth_score": row.get("growth_score"),
        "opportunity_score": row.get("opportunity_score"),
        "opportunity_label": row.get("opportunity_label"),
        "trend_arrow": row.get("trend_arrow"),
    }
    return out


def _collect_mapped_products() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    mapping_payload = load_fastmoss_mapping()
    mappings = [
        row
        for row in (mapping_payload.get("mappings") or [])
        if str(row.get("mapping_status") or "").upper() == MAPPING_MAPPED
        and str(row.get("fastmoss_shop_id") or "").strip()
    ]

    products: list[dict[str, Any]] = []
    shop_errors: list[str] = []
    shop_collections: list[dict[str, Any]] = []
    endpoints_used = {f"{_base_url()}{GOODS_PATH}"}

    for mapping in mappings:
        fastmoss_shop_id = str(mapping["fastmoss_shop_id"]).strip()
        shop_name = str(mapping.get("shop_name") or fastmoss_shop_id)
        try:
            payload = fetch_shop_goods_catalog(
                fastmoss_shop_id,
                max_products=RADAR_MAX_PRODUCTS,
                page_size=RADAR_PAGE_SIZE,
            )
        except Exception as exc:
            logger.warning("FastMoss goods fetch failed for %s: %s", fastmoss_shop_id, exc)
            shop_errors.append(f"{shop_name}: {exc}")
            continue

        shop_collections.append(
            {
                "shop_id": str(mapping.get("shop_id") or ""),
                "shop_name": shop_name,
                "fastmoss_shop_id": fastmoss_shop_id,
                "products_collected": payload.get("products_collected")
                or payload.get("product_count")
                or 0,
                "product_count_total": payload.get("product_count_total"),
                "pages_collected": payload.get("pages_collected") or 0,
            }
        )

        for product in payload.get("products") or []:
            key = product.get("product_id") or product.get("product_link")
            if not key:
                continue
            products.append(
                {
                    **product,
                    "seller_shop_id": str(mapping.get("shop_id") or ""),
                    "seller_shop_name": mapping.get("shop_name") or product.get("shop_name"),
                    "fastmoss_shop_id": fastmoss_shop_id,
                }
            )

    meta = {
        "endpoints": sorted(endpoints_used),
        "shops_scanned": len(mappings),
        "shops_with_errors": len(shop_errors),
        "shop_errors": shop_errors[:10],
        "products_collected": len(products),
        "max_products_per_shop": RADAR_MAX_PRODUCTS,
        "page_size": RADAR_PAGE_SIZE,
        "shop_collections": shop_collections,
    }
    return products, meta


def build_tiktok_product_radar(*, force_refresh: bool = False) -> dict[str, Any]:
    global _cache_payload, _cache_ts

    if (
        not force_refresh
        and _cache_payload is not None
        and (time.time() - _cache_ts) < RADAR_CACHE_SEC
    ):
        return _cache_payload

    raw_products, fetch_meta = _collect_mapped_products()
    enriched = enrich_product_metrics(raw_products)

    top_100 = sorted(enriched, key=_sort_key_sales, reverse=True)[:100]
    top_new = sorted(
        [p for p in enriched if p.get("is_new_product")],
        key=_sort_key_sales,
        reverse=True,
    )[:RADAR_TOP_NEW]
    top_growth = sorted(enriched, key=lambda p: float(p.get("growth_score") or 0), reverse=True)[
        :RADAR_TOP_GROWTH
    ]
    top_opportunities = sorted(
        enriched,
        key=lambda p: float(p.get("opportunity_score") or 0),
        reverse=True,
    )[:RADAR_TOP_OPPORTUNITIES]

    shops = sorted(
        {
            (p.get("seller_shop_id"), p.get("seller_shop_name"))
            for p in enriched
            if p.get("seller_shop_id")
        },
        key=lambda row: row[1] or "",
    )
    categories = sorted({_uncategorized(p.get("category")) for p in enriched})
    shop_view = _build_shop_view(enriched)
    category_dashboard = _build_category_dashboard(enriched)

    payload = {
        "module": "assortment_intelligence",
        "version": "v1",
        "status": "tiktok_product_radar",
        "strategy": "fastmoss_only",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "fastmoss": fetch_meta,
        "portfolio": {
            "total_products": len(enriched),
            "new_products_20d": sum(1 for p in enriched if p.get("is_new_product")),
            "growth_products": len(top_growth),
            "opportunity_products": len(top_opportunities),
        },
        "filters": {
            "shops": [{"shop_id": sid, "shop_name": name} for sid, name in shops],
            "categories": categories,
            "new_product_days": NEW_PRODUCT_DAYS,
        },
        "top_100": [_public_product(p, rank=i + 1) for i, p in enumerate(top_100)],
        "top_new": [_public_product(p, rank=i + 1) for i, p in enumerate(top_new)],
        "top_growth": [_public_product(p, rank=i + 1) for i, p in enumerate(top_growth)],
        "top_opportunities": [_public_product(p, rank=i + 1) for i, p in enumerate(top_opportunities)],
        "shop_view": shop_view,
        "category_dashboard": category_dashboard,
    }

    _cache_payload = payload
    _cache_ts = time.time()
    return payload


def clear_tiktok_radar_cache() -> None:
    """Drop in-memory TikTok Product Radar payload (sheet/FastMoss derived)."""
    global _cache_payload, _cache_ts
    _cache_payload = None
    _cache_ts = 0.0
