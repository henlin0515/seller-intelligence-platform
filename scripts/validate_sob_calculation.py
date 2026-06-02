#!/usr/bin/env python3
"""Phase 3-B: validate SOB calculation for Business Intelligence rows."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from seller.intelligence.business.meta import (  # noqa: E402
    get_business_intelligence_payload,
    validate_sob_rows,
)
from seller.intelligence.business.shopee_adgmv import get_shopee_adgmv  # noqa: E402
from seller.intelligence.seller_master import get_seller_master  # noqa: E402


def main() -> int:
    master = get_seller_master()
    tracker = get_shopee_adgmv()
    rows = get_business_intelligence_payload(master, tracker)
    validation = validate_sob_rows(rows)

    examples = [
        row
        for row in rows
        if row.get("mtd_shopee_sob_percent") is not None
        and row.get("mtd_tiktok_sob_percent") is not None
    ][:10]

    print("=== SOB validation ===")
    print(f"Total rows calculated: {validation['total_rows_calculated']}")
    print()
    print("First 10 SOB examples:")
    for row in examples:
        print(
            json.dumps(
                {
                    "shop_name": row["shop_name"],
                    "shopee_mtd_adgmv_usd": row["shopee_mtd_adgmv_usd"],
                    "tiktok_mtd_adgmv_usd": row["tiktok_mtd_adgmv_usd"],
                    "mtd_shopee_sob_percent": row["mtd_shopee_sob_percent"],
                    "mtd_tiktok_sob_percent": row["mtd_tiktok_sob_percent"],
                    "m1_shopee_sob_percent": row["m1_shopee_sob_percent"],
                    "m1_tiktok_sob_percent": row["m1_tiktok_sob_percent"],
                    "mtd_total": round(
                        (row["mtd_shopee_sob_percent"] or 0)
                        + (row["mtd_tiktok_sob_percent"] or 0),
                        1,
                    ),
                    "m1_total": round(
                        (row["m1_shopee_sob_percent"] or 0)
                        + (row["m1_tiktok_sob_percent"] or 0),
                        1,
                    ),
                },
                ensure_ascii=False,
            )
        )

    print()
    print("Validation result:")
    print(f"  MTD pairs checked: {validation['mtd_pairs_checked']} passed: {validation['mtd_passed']}")
    print(f"  M-1 pairs checked: {validation['m1_pairs_checked']} passed: {validation['m1_passed']}")
    print(f"  100% check: {'PASS' if validation['passed'] else 'FAIL'}")
    if validation["mtd_failures"]:
        print("  MTD failures:", validation["mtd_failures"])
    if validation["m1_failures"]:
        print("  M-1 failures:", validation["m1_failures"])

    return 0 if validation["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
