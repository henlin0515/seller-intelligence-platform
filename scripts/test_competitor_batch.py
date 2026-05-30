#!/usr/bin/env python3
"""Test profile -> shop search pipeline for named competitors."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv()

from seller.competitor_tracker.service import check_tiktok_shop, find_competitor_by_name
from seller.competitor_tracker.sheet import load_competitors_from_sheet as _load


def main() -> int:
    names = sys.argv[1:] if len(sys.argv) > 1 else ["Mumu", "LaLa", "Sklyer", "Stompion"]
    rows, meta = _load()
    print("sheet meta:", {k: v for k, v in meta.items() if not str(k).startswith("_")})
    tested = 0
    for q in names:
        matches = find_competitor_by_name(q)
        if not matches:
            print(f"\n--- No row for '{q}' ---")
            continue
        row = matches[0]
        print(f"\n=== {row['shop_name']} ({row['shop_id']}) ===")
        print(f"Profile: {row['tiktok_link']}")
        result = check_tiktok_shop(row)
        out = json.dumps(result, indent=2, ensure_ascii=False)[:2500]
        sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
        tested += 1
    print(f"\nTested {tested} shop(s).")
    return 0 if tested else 1


if __name__ == "__main__":
    raise SystemExit(main())
