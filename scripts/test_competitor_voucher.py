#!/usr/bin/env python3
"""Smoke test: load COMPETITOR_TRACKER and check up to 3 TikTok links."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv()

from seller.competitor_tracker.sheet import load_competitors_from_sheet
from seller.competitor_tracker.service import check_tiktok_shop


def main() -> int:
    rows, meta = load_competitors_from_sheet()
    print("meta:", {k: v for k, v in meta.items() if not k.startswith("_")})
    if not rows:
        print("No rows — configure Google Sheets and COMPETITOR_TRACKER tab.")
        return 1

    sample = rows[:3]
    print(f"Checking {len(sample)} shop(s)...")
    for row in sample:
        result = check_tiktok_shop(row)
        print(
            f"  {row['shop_id']} | {row['shop_name'][:40]} | "
            f"{result['voucher_status']} | {result.get('voucher_text', '')[:60]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
