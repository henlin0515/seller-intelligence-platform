#!/usr/bin/env python3
"""Validate TikTok Product Radar payload."""

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

    print("=== TIKTOK PRODUCT RADAR ===")
    print("1. FastMoss endpoints used")
    for endpoint in fm.get("endpoints") or []:
        print(f"   {endpoint}")

    print(f"\n2. Product count collected: {fm.get('products_collected', 0)}")
    print(f"3. New product count (20D): {portfolio.get('new_products_20d', 0)}")
    print(f"4. Growth product count: {portfolio.get('growth_products', 0)}")
    print(f"5. Opportunity count: {portfolio.get('opportunity_products', 0)}")
    print(f"   Shops scanned: {fm.get('shops_scanned', 0)}")
    print(f"   Top 100 rows: {len(payload.get('top_100') or [])}")

    out = ROOT / "_tmp_tiktok_radar.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2)[:900000], encoding="utf-8")
    print(f"\nSaved {out.name}")
    return 0 if fm.get("products_collected") else 1


if __name__ == "__main__":
    raise SystemExit(main())
