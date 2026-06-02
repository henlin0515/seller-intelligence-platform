#!/usr/bin/env python3
"""Apply locked manual FastMoss mapping overrides and refresh TikTok BI."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seller.fastmoss.review import apply_manual_mapping_override  # noqa: E402
from seller.intelligence.refresh_data import refresh_tiktok_bi_for_shop_ids  # noqa: E402

OVERRIDES = [
    {
        "shop_id": "383771904",
        "tiktok_shop_name": "Eight Persent Store",
        "fastmoss_shop_id": "7494670296136190188",
        "fastmoss_shop_name": "Eight Persent Store",
        "fastmoss_shop_url": "https://www.fastmoss.com/shop-marketing/detail/7494670296136190188",
        "notes": "Manual override: Eight Persent Store ↔ Eight Persent Store",
    },
    {
        "shop_id": "64329852",
        "tiktok_shop_name": "LALA",
        "fastmoss_shop_id": "7494929890907294497",
        "fastmoss_shop_name": "LALA",
        "fastmoss_shop_url": "https://www.fastmoss.com/shop-marketing/detail/7494929890907294497",
        "notes": "Manual override: LALA ↔ LALA",
    },
]


def main() -> int:
    results: list[dict] = []
    shop_ids: list[str] = []
    for item in OVERRIDES:
        shop_ids.append(item["shop_id"])
        result = apply_manual_mapping_override(
            item["shop_id"],
            tiktok_shop_name=item["tiktok_shop_name"],
            fastmoss_shop_id=item["fastmoss_shop_id"],
            fastmoss_shop_name=item["fastmoss_shop_name"],
            fastmoss_shop_url=item["fastmoss_shop_url"],
            confidence=1.0,
            notes=item["notes"],
        )
        results.append(result)

    bi_result = refresh_tiktok_bi_for_shop_ids(shop_ids)
    report = {
        "overrides": results,
        "tiktok_bi": bi_result,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
