from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from seller.assortment.db import get_session
from seller.assortment.models import CompetitorProduct, ImportBatch, OurProduct

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
    }


def _parse_price(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(str(val).replace(",", "").replace("₱", "").strip())
    except (TypeError, ValueError):
        return None


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
    mark_as_new: bool = True,
) -> dict[str, Any]:
    """
    Manual import — future scraper will call the same function with source_type='scraper'.
    """
    session = get_session()
    now = datetime.now(timezone.utc)
    try:
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
        new_count = 0
        for raw in products:
            row = _normalize_row(raw)
            if not row["product_name"]:
                continue
            ext_key = row["product_link"] or row["product_name"]
            existing = None
            if ext_key:
                existing = (
                    session.query(CompetitorProduct)
                    .filter(CompetitorProduct.external_key == ext_key)
                    .first()
                )

            if existing:
                existing.last_seen_at = now
                existing.price = row["price"] if row["price"] is not None else existing.price
                existing.product_image_url = row["product_image_url"] or existing.product_image_url
                existing.sku_variations = row["sku_variations"] or existing.sku_variations
                is_new = False
            else:
                session.add(
                    CompetitorProduct(
                        import_batch_id=batch.id,
                        competitor_shop_id=competitor_shop_id,
                        product_name=row["product_name"],
                        product_link=row["product_link"],
                        product_image_url=row["product_image_url"],
                        sku_variations=row["sku_variations"],
                        price=row["price"],
                        first_detected_at=now,
                        last_seen_at=now,
                        is_new_listing=mark_as_new,
                        external_key=ext_key,
                    )
                )
                is_new = True
                new_count += 1
            count += 1

        batch.product_count = count
        session.commit()
        return {
            "ok": True,
            "import_batch_id": batch.id,
            "imported": count,
            "new_listings": new_count,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
