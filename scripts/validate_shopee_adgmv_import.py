#!/usr/bin/env python3
"""Phase 3-A: validate Shopee ADGMV Tracker import into Business Intelligence."""

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
    get_shopee_adgmv_match_summary,
)
from seller.intelligence.business.shopee_adgmv import get_shopee_adgmv  # noqa: E402
from seller.intelligence.seller_master import get_seller_master  # noqa: E402


def main() -> int:
    master = get_seller_master(force_refresh=True)
    tracker = get_shopee_adgmv(force_refresh=True)
    summary = get_shopee_adgmv_match_summary(master, tracker)
    sellers = get_business_intelligence_payload(master, tracker)

    matched_rows = [s for s in sellers if s.get("shopee_data_status") == "available"]

    print("=== Shopee ADGMV import validation ===")
    print(f"Tracker tab: {summary['tab']}")
    print(f"Total Tracker rows: {summary['total_tracker_rows']}")
    print(f"Total matched shops: {summary['total_matched_shops']}")
    print(f"Total unmatched shops: {summary['total_unmatched_shops']}")
    print()
    print("First 10 matched shops:")
    for row in matched_rows[:10]:
        print(
            json.dumps(
                {
                    "shop_name": row["shop_name"],
                    "tracker_shop_name": row["tracker_shop_name"],
                    "shopee_mtd_adgmv_usd": row["shopee_mtd_adgmv_usd"],
                    "shopee_m1_adgmv_usd": row["shopee_m1_adgmv_usd"],
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
