#!/usr/bin/env python3
"""Backfill failed FastMoss BI shops using anonymous + retry strategy."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from seller.intelligence.business.collector import collect_mapped_shop_tiktok  # noqa: E402
from seller.intelligence.business.store import (  # noqa: E402
    load_business_intelligence_data,
    save_business_intelligence_data,
)
from seller.intelligence.periods import resolve_periods  # noqa: E402


def main() -> None:
    from datetime import date

    data = load_business_intelligence_data()
    if not data:
        raise SystemExit("No business_intelligence_data.json")
    today = date.today()
    periods = resolve_periods(today)

    sellers = list(data.get("sellers") or [])
    failed_idx = [i for i, s in enumerate(sellers) if s.get("status") != "success"]
    print(f"backfill start failed={len(failed_idx)} total={len(sellers)} periods={periods.as_dict()}")

    recovered = 0
    still = 0
    for n, idx in enumerate(failed_idx, start=1):
        row = sellers[idx]
        mapping = {
            "shop_id": row.get("shop_id"),
            "shop_name": row.get("shop_name"),
            "tiktok_shop_name": row.get("tiktok_shop_name"),
            "fastmoss_shop_id": row.get("fastmoss_shop_id"),
            "fastmoss_shop_name": row.get("fastmoss_shop_name"),
        }
        label = str(mapping.get("shop_name") or mapping.get("shop_id") or "").encode(
            "ascii", "replace"
        ).decode("ascii")
        print(f"[{n}/{len(failed_idx)}] {label} ...", flush=True)
        collected = collect_mapped_shop_tiktok(mapping, periods, delay_sec=0, session=None)
        sellers[idx] = collected
        if collected.get("status") == "success":
            recovered += 1
            print(
                f"  OK mtd={collected.get('mtd_gmv_php')} m1={collected.get('m1_gmv_php')}",
                flush=True,
            )
        else:
            still += 1
            err = str(collected.get("error") or "").encode("ascii", "replace").decode("ascii")
            print(f"  FAIL {err}", flush=True)
        # Persist incrementally so progress is not lost.
        success = sum(1 for s in sellers if s.get("status") == "success")
        data["sellers"] = sellers
        data["summary"] = {
            "processed": len(sellers),
            "success": success,
            "failed": len(sellers) - success,
            "approved_only": True,
        }
        data["cache_status"] = "ready" if success else data.get("cache_status")
        data["periods"] = periods.as_dict()
        data["reference_today"] = today.isoformat()
        data["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save_business_intelligence_data(data)
        time.sleep(1.0)

    print(f"DONE recovered={recovered} still_failed={still} success_total={data['summary']['success']}")


if __name__ == "__main__":
    main()
