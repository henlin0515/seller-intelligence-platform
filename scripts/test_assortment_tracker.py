#!/usr/bin/env python3
"""Test Competitor Assortment ↔ COMPETITOR_TRACKER integration (no Playwright required)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from seller.assortment.db import init_assortment_db
from seller.assortment.tracker_sync import get_tracker_payload, sync_tracker_catalog
from seller.competitor_tracker.sheet import load_competitors_from_sheet


def main() -> int:
    init_assortment_db()
    rows, meta = load_competitors_from_sheet()
    print("=== Tracker sheet ===")
    print(json.dumps(meta, indent=2, default=str))
    print(f"Rows loaded: {len(rows)}")
    for r in rows[:10]:
        print(f"  - {r.get('shop_name')} ({r.get('shop_id')}) shopee={bool(r.get('shopee_link'))} tiktok={bool(r.get('tiktok_link'))}")

    print("\n=== Sync from tracker (fetch catalogs) ===")
    sync = sync_tracker_catalog(run_matching=True)
    print(json.dumps(
        {
            "ok": sync.get("ok"),
            "sheet": sync.get("sheet"),
            "processed": sync.get("processed"),
            "catalog_ok": sync.get("catalog_ok"),
            "catalog_na": sync.get("catalog_na"),
            "products_imported": sync.get("products_imported"),
            "has_competitor_data": sync.get("has_competitor_data"),
            "matching": sync.get("matching"),
        },
        indent=2,
        default=str,
    ))

    for r in sync.get("results") or []:
        print(f"\n  Row {r.get('row_number')} {r.get('seller_name')}")
        print(f"    Shopee Link: {r.get('shopee_link')}")
        print(f"    TikTok Link: {r.get('tiktok_link')}")
        print(f"    Shopee Status: {r.get('shopee_status')}  products: {r.get('shopee_products_found', 0)}")
        if r.get("shopee_status") == "NA":
            print(f"    Shopee Reason: {r.get('shopee_reason')}")
        print(f"    TikTok Status: {r.get('tiktok_status')}  products: {r.get('tiktok_products_found', 0)}")
        if r.get("tiktok_status") == "NA":
            print(f"    TikTok Reason: {r.get('tiktok_reason')}")
        cmp = r.get("comparison") or {}
        if cmp:
            print(f"    Compare: {cmp}")

    payload = get_tracker_payload()
    print("\n=== API tracker payload summary ===")
    print(f"configured={payload.get('configured')} sheet_error={payload.get('sheet_error')}")
    print(f"has_competitor_data={payload.get('has_competitor_data')} sellers={len(payload.get('sellers') or [])}")

    return 0 if meta.get("error") is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
