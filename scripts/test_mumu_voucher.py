#!/usr/bin/env python3
"""Debug check for Mumu PH (or name substring) from COMPETITOR_TRACKER."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv()

from seller.competitor_tracker.service import check_tiktok_shop, find_competitor_by_name


def main() -> int:
    query = sys.argv[1] if len(sys.argv) > 1 else "Mumu"
    rows = find_competitor_by_name(query)
    if not rows:
        print(f"No competitor matching '{query}'")
        return 1
    row = rows[0]
    print(f"Shop: {row['shop_name']} ({row['shop_id']})")
    print(f"TikTok: {row['tiktok_link']}")
    result = check_tiktok_shop(row)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
