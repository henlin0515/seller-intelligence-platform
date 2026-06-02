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


def _safe_print(text: str) -> None:
    """Avoid Windows cp950 console crashes on shop names with special chars."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8", errors="replace"
        ))


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
    validation = payload.get("validation") or {}
    ds = payload.get("data_source") or {}
    print(f"Sheet tab: {ds.get('seller_master_tab', '—')}")
    print(f"Spreadsheet: {ds.get('spreadsheet_id', '—')}")
    print(f"Data status: {validation.get('data_status', '—')}")
    if validation.get("message"):
        print(f"Message: {validation.get('message')}")
    print(f"Seller master rows: {validation.get('seller_master_row_count', '—')}")
    print(f"Approved shops: {validation.get('approved_shop_count', '—')}")
    print(f"Raw FastMoss rows: {validation.get('raw_record_count', '—')}")
    print(f"Mapped products: {validation.get('mapped_product_count', '—')}")
    print(f"Shop filter count: {validation.get('shop_count', '—')}")
    print(f"Category count: {validation.get('category_count', '—')}")
    print("1. FastMoss endpoints used")
    for endpoint in fm.get("endpoints") or []:
        print(f"   {endpoint}")

    print(f"\n2. Product count collected: {fm.get('products_collected', 0)}")
    print(f"3. Shop View shops: {len(shops)}")
    print(f"4. Category groups: {len(categories)}")
    print(f"5. New products (20D): {portfolio.get('new_products_20d', 0)}")
    collections = fm.get("shop_collections") or []
    if collections:
        print("\nFastMoss collector validation:")
        _safe_print(f"{'Shop':<28} {'Products collected':>18} {'Pages collected':>16}")
        _safe_print("-" * 64)
        for row in collections:
            _safe_print(
                f"{str(row.get('shop_name') or '—'):<28} "
                f"{int(row.get('products_collected') or 0):>18} "
                f"{int(row.get('pages_collected') or 0):>16}"
            )
        mumu = next((r for r in collections if str(r.get("shop_name") or "").strip() == "Mumu PH"), None)
        if mumu:
            print(
                f"\nExample — Mumu PH: {mumu.get('products_collected')} products, "
                f"{mumu.get('pages_collected')} pages "
                f"(FastMoss total {mumu.get('product_count_total')})"
            )
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
