"""Demo Seller Intelligence V1 — business calculations + SOB validation."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seller.intelligence import get_seller_intelligence_v1_snapshot
from seller.intelligence.periods import resolve_periods


def _sob_totals_100(record: dict) -> bool:
    for shopee_key, tiktok_key in (
        ("mtd_shopee_sob_percent", "mtd_tiktok_sob_percent"),
        ("m1_shopee_sob_percent", "m1_tiktok_sob_percent"),
    ):
        s = record.get(shopee_key)
        t = record.get(tiktok_key)
        if s is None or t is None:
            continue
        if abs((s + t) - 100.0) > 0.01:
            return False
    return True


def main() -> int:
    snap = get_seller_intelligence_v1_snapshot(reference_today=date(2026, 6, 7))
    business = snap["business_intelligence"]
    example = business[0]

    print("=== Period logic (today=2026-06-07) ===")
    print(json.dumps(resolve_periods(date(2026, 6, 7)).as_dict(), indent=2))
    print()
    print("=== Period logic (today=2026-06-01) ===")
    print(json.dumps(resolve_periods(date(2026, 6, 1)).as_dict(), indent=2))
    print()
    print("=== Example seller (business_intelligence[0]) ===")
    print(json.dumps(example, indent=2))
    print()

    all_ok = all(_sob_totals_100(r) for r in business)
    print(f"SOB pairs total 100% for all {len(business)} sellers: {all_ok}")
    if example["mtd_shopee_sob_percent"] is not None:
        mtd_sum = example["mtd_shopee_sob_percent"] + example["mtd_tiktok_sob_percent"]
        print(f"  Example MTD SOB sum: {mtd_sum}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
