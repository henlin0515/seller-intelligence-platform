#!/usr/bin/env python3
"""Validate TikTok Product Radar shop/category structure."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from seller.intelligence.assortment.radar import build_tiktok_product_radar  # noqa: E402


def main() -> int:
    payload = build_tiktok_product_radar(force_refresh=True)
    fm = payload.get("fastmoss") or {}
    portfolio = payload.get("portfolio") or {}
    shop_view = payload.get("shop_view") or {}
    category_dashboard = payload.get("category_dashboard") or {}

    shops = shop_view.get("shops") or []
    categories = category_dashboard.get("categories") or []
    first_shop = shops[0] if shops else {}
    first_category = categories[0]["category"] if categories else None
    category_detail = (
        category_dashboard.get("category_details", {}).get(first_category, {})
        if first_category
        else {}
    )

    print("=== TIKTOK PRODUCT RADAR ===")
    print("1. FastMoss endpoints used")
    for endpoint in fm.get("endpoints") or []:
        print(f"   {endpoint}")

    print(f"\n2. Product count collected: {fm.get('products_collected', 0)}")
    print(f"3. Shop View shops: {len(shops)}")
    print(f"4. Category groups: {len(categories)}")
    print(f"5. New products (20D): {portfolio.get('new_products_20d', 0)}")
    if first_shop:
        print(
            f"6. Sample shop sections: top={len(first_shop.get('top_products') or [])} "
            f"new={len(first_shop.get('new_products') or [])} "
            f"growth={len(first_shop.get('growth_products') or [])} "
            f"opp={len(first_shop.get('opportunity_products') or [])}"
        )
    if first_category:
        print(
            f"7. Sample category ({first_category}): top={len(category_detail.get('top_products') or [])} "
            f"new={len(category_detail.get('new_products') or [])} "
            f"growth={len(category_detail.get('growth_products') or [])} "
            f"shops={len(category_detail.get('top_shops') or [])}"
        )

    out = ROOT / "_tmp_tiktok_radar.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2)[:900000], encoding="utf-8")
    print(f"\nSaved {out.name}")

    ok = bool(fm.get("products_collected")) and bool(shops) and bool(categories)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
