#!/usr/bin/env python3
"""Phase 2-C: collect FastMoss TikTok GMV for all MAPPED shops."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seller.intelligence.business.calculations import (  # noqa: E402
    mom_percent,
    tiktok_php_to_usd,
)
from seller.intelligence.business.collector import collect_all_mapped_shops  # noqa: E402
from seller.intelligence.business.store import save_business_intelligence_data  # noqa: E402


def main() -> int:
    payload = collect_all_mapped_shops()
    out_path = save_business_intelligence_data(payload)

    summary = payload["summary"]
    print(f"Saved: {out_path}")
    print(f"Shops processed: {summary['processed']}")
    print(f"Success: {summary['success']}")
    print(f"Failed: {summary['failed']}")
    print()
    print("First 10 data rows:")
    for row in payload["sellers"][:10]:
        if row.get("status") != "success":
            print(
                json.dumps(
                    {
                        "shop_id": row["shop_id"],
                        "shop_name": row["shop_name"],
                        "status": row["status"],
                        "error": row.get("error"),
                    },
                    ensure_ascii=False,
                )
            )
            continue
        mtd_usd = tiktok_php_to_usd(row["tiktok_mtd_adgmv_php"])
        m1_usd = tiktok_php_to_usd(row["tiktok_m1_adgmv_php"])
        mom = mom_percent(mtd_usd, m1_usd)
        print(
            json.dumps(
                {
                    "shop_id": row["shop_id"],
                    "shop_name": row["shop_name"],
                    "tiktok_shop_name": row["tiktok_shop_name"],
                    "mtd_gmv_php": row["mtd_gmv_php"],
                    "m1_gmv_php": row["m1_gmv_php"],
                    "tiktok_mtd_adgmv_php": row["tiktok_mtd_adgmv_php"],
                    "tiktok_m1_adgmv_php": row["tiktok_m1_adgmv_php"],
                    "tiktok_mtd_adgmv_usd": round(mtd_usd, 4),
                    "tiktok_m1_adgmv_usd": round(m1_usd, 4),
                    "tiktok_mom_percent": round(mom, 4) if mom is not None else None,
                    "status": row["status"],
                },
                ensure_ascii=False,
            )
        )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
