from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from seller.assortment.constants import PLATFORM_SHOPEE, PLATFORM_TIKTOK
from seller.assortment.db import get_session
from seller.assortment.models import CompetitorProduct, ImportBatch, OurProduct, ProductMatch

logger = logging.getLogger("seller.assortment.import")


def _serialize_sku(sku: Any) -> str | None:
    if sku is None:
        return None
    if isinstance(sku, list):
        return json.dumps(sku, ensure_ascii=False)
    if isinstance(sku, str):
        s = sku.strip()
        if s.startswith("["):
            return s
        parts = [p.strip() for p in s.replace("|", ",").split(",") if p.strip()]
        return json.dumps(parts, ensure_ascii=False) if parts else None
    return json.dumps([str(sku)], ensure_ascii=False)


def _parse_price(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(str(val).replace(",", "").replace("₱", "").strip())
    except (TypeError, ValueError):
        return None


def _parse_listed_at(val: Any) -> datetime | None:
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    s = str(val).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s[:19], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_name": str(row.get("product_name") or row.get("name") or "").strip(),
        "product_link": (row.get("product_link") or row.get("link") or "").strip() or None,
        "product_image_url": (
            row.get("product_image_url") or row.get("image_url") or row.get("image") or ""
        ).strip()
        or None,
        "sku_variations": _serialize_sku(row.get("sku_variations") or row.get("sku")),
        "price": _parse_price(row.get("price")),
        "listed_at": _parse_listed_at(row.get("listed_at") or row.get("listed_date")),
    }


def clear_shop_catalog(session, shop_id: str) -> None:
    """Remove prior products and matches for one tracker shop pair before re-sync."""
    product_ids = [
        p.id
        for p in session.query(CompetitorProduct.id).filter(
            CompetitorProduct.competitor_shop_id == shop_id
        )
    ]
    if product_ids:
        session.query(ProductMatch).filter(
            (ProductMatch.tiktok_product_id.in_(product_ids))
            | (ProductMatch.shopee_product_id.in_(product_ids))
            | (ProductMatch.competitor_product_id.in_(product_ids))
        ).delete(synchronize_session=False)
        session.query(CompetitorProduct).filter(
            CompetitorProduct.competitor_shop_id == shop_id
        ).delete(synchronize_session=False)


def import_shop_platform_products(
    products: list[dict[str, Any]],
    *,
    platform: str,
    competitor_shop_id: str,
    competitor_shop_name: str | None = None,
    label: str = "tracker-sync",
    replace_shop: bool = False,
) -> dict[str, Any]:
    """Import Shopee or TikTok catalog for one COMPETITOR_TRACKER shop pair."""
    session = get_session()
    now = datetime.now(timezone.utc)
    try:
        if replace_shop:
            clear_shop_catalog(session, competitor_shop_id)

        batch = ImportBatch(
            label=label,
            source_type="manual",
            catalog_type="competitor",
            competitor_shop_id=competitor_shop_id,
            competitor_shop_name=competitor_shop_name,
            product_count=0,
        )
        session.add(batch)
        session.flush()

        count = 0
        for raw in products:
            row = _normalize_row(raw)
            if not row["product_name"]:
                continue
            ext_key = f"{platform}:{competitor_shop_id}:{row['product_link'] or row['product_name']}"
            listed = row["listed_at"] or now
            session.add(
                CompetitorProduct(
                    import_batch_id=batch.id,
                    competitor_shop_id=competitor_shop_id,
                    competitor_shop_name=competitor_shop_name,
                    platform=platform,
                    product_name=row["product_name"],
                    product_link=row["product_link"],
                    product_image_url=row["product_image_url"],
                    sku_variations=row["sku_variations"],
                    price=row["price"],
                    listed_at=listed,
                    first_detected_at=now,
                    last_seen_at=now,
                    is_new_listing=False,
                    external_key=ext_key,
                )
            )
            count += 1

        batch.product_count = count
        session.commit()
        return {"ok": True, "import_batch_id": batch.id, "imported": count, "platform": platform}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def import_our_products(
    products: list[dict[str, Any]],
    *,
    label: str = "manual",
) -> dict[str, Any]:
    session = get_session()
    try:
        batch = ImportBatch(
            label=label,
            source_type="manual",
            catalog_type="our",
            product_count=0,
        )
        session.add(batch)
        session.flush()

        count = 0
        for raw in products:
            row = _normalize_row(raw)
            if not row["product_name"]:
                continue
            session.add(
                OurProduct(
                    import_batch_id=batch.id,
                    product_name=row["product_name"],
                    product_link=row["product_link"],
                    product_image_url=row["product_image_url"],
                    sku_variations=row["sku_variations"],
                    price=row["price"],
                )
            )
            count += 1
        batch.product_count = count
        session.commit()
        return {"ok": True, "import_batch_id": batch.id, "imported": count}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def import_competitor_products(
    products: list[dict[str, Any]],
    *,
    label: str = "manual",
    competitor_shop_id: str | None = None,
    competitor_shop_name: str | None = None,
    platform: str = PLATFORM_TIKTOK,
    mark_as_new: bool = True,
    replace_shop: bool = False,
) -> dict[str, Any]:
    """Backward-compatible import — defaults to TikTok platform."""
    if not competitor_shop_id:
        return import_shop_platform_products(
            products,
            platform=platform,
            competitor_shop_id="unknown",
            competitor_shop_name=competitor_shop_name,
            label=label,
            replace_shop=replace_shop,
        )
    return import_shop_platform_products(
        products,
        platform=platform,
        competitor_shop_id=competitor_shop_id,
        competitor_shop_name=competitor_shop_name,
        label=label,
        replace_shop=replace_shop,
    )
