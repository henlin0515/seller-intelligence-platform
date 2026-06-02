#!/usr/bin/env python3
"""Validate Seller Performance uses AI data tab (Kinwooph smoke test)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from seller.metric_resolver import build_dashboard_from_raw, shop_info_from_raw  # noqa: E402
from seller.raw_data import get_raw_shop_row, search_raw_shops  # noqa: E402
from seller.sheets_cache import refresh  # noqa: E402


def main() -> int:
    status = refresh(force=True)
    data_source = status.get("data_source")
    primary_tab = status.get("primary_tab")
    seller_count = status.get("seller_count")

    print("=== SELLER PERFORMANCE DATA SOURCE ===")
    print(f"1. Data source used: {data_source}")
    print(f"   Primary tab: {primary_tab}")
    print(f"   Sellers loaded: {seller_count}")

    results = search_raw_shops("Kinwooph")
    if not results:
        print("Search Kinwooph: NO RESULTS")
        return 1
    match = results[0]
    print("\n2. Search Kinwooph:")
    print(f"   Shop ID: {match.get('shop_id')}")
    print(f"   Shop Name: {match.get('shop_name')}")

    if str(match.get("shop_id")) != "62404318" or match.get("shop_name") != "Kinwooph":
        print("   ERROR: unexpected search match")
        return 1

    entry = get_raw_shop_row("62404318")
    if not entry:
        print("Dashboard row load failed")
        return 1

    raw = entry["raw"]
    meta = shop_info_from_raw(raw, entry["shop_id"], entry.get("shop_name", ""))
    dashboard = build_dashboard_from_raw(raw)
    shop_info = next(s for s in dashboard["sections"] if s["key"] == "shop_info")

    print("\n3. Matched row fields:")
    for key in (
        "shop_id",
        "shop_name",
        "bu",
        "lead",
        "rm_kam",
        "category",
        "tier",
        "shop_link",
    ):
        print(f"   {key}: {meta.get(key) or raw.get(key.title()) or '—'}")

    populated = []
    missing = []
    expected_labels = [
        "Shop ID",
        "Shop Name",
        "Managed Tier",
        "BU",
        "Lead",
        "RM/KAM",
        "BD Category",
        "BI Category",
        "Shop Link",
        "Seller Penalty Points",
        "MTD FSP",
        "MTD PP",
    ]
    metrics = {m["label"]: m for m in shop_info.get("metrics", [])}
    for label in expected_labels:
        metric = metrics.get(label)
        display = metric.get("mtd_display") if metric else None
        if display and display != "N/A":
            populated.append(label)
        else:
            missing.append(label)

    print("\n4. Shop Info metrics populated:")
    print(f"   {', '.join(populated) if populated else 'none'}")
    if missing:
        print(f"   Optional/missing in sheet: {', '.join(missing)}")

    ok = (
        data_source == "google_sheets_ai_data"
        and primary_tab == "AI data"
        and str(meta.get("shop_id")) == "62404318"
        and meta.get("shop_name") == "Kinwooph"
        and meta.get("bu") not in (None, "", "N/A")
        and meta.get("lead") not in (None, "", "N/A")
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
