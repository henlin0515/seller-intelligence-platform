#!/usr/bin/env python3
"""
Refresh + validate FastMoss TikTok BI for every approved mapping (strict freshness).

Usage:
  python scripts/validate_fastmoss_bi.py
  python scripts/validate_fastmoss_bi.py --skip-refresh   # validate cache only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-refresh",
        action="store_true",
        help="Only validate existing business_intelligence_data.json",
    )
    parser.add_argument(
        "--delay-sec",
        type=float,
        default=float(os.getenv("BI_VALIDATE_DELAY_SEC", "1.0")),
    )
    args = parser.parse_args()

    from seller.fastmoss.review import approved_mapping_rows
    from seller.intelligence.business.bi_cache_refresh import (
        BiCacheRefreshError,
        refresh_bi_cache,
    )
    from seller.intelligence.business.bi_validation import (
        format_validation_summary,
        validate_bi_sellers,
    )
    from seller.intelligence.business.store import (
        load_business_intelligence_data,
        save_business_intelligence_data,
    )
    from seller.intelligence.business_time import business_today
    from seller.intelligence.periods import resolve_periods

    today = business_today()
    periods = resolve_periods(today)
    approved = approved_mapping_rows()
    print(
        f"validate_fastmoss_bi today={today} approved={len(approved)} "
        f"MTD={periods.mtd.start}..{periods.mtd.end} M1={periods.m1.start}..{periods.m1.end}",
        flush=True,
    )

    if not args.skip_refresh:
        print(f"=== refresh delay={args.delay_sec}s (strict freshness, no stale fallback) ===", flush=True)
        try:
            result = refresh_bi_cache(
                delay_sec=args.delay_sec,
                reference_today=today,
                trigger="validate_fastmoss_bi",
                skip_healthcheck=False,
                invalidate_first=False,
            )
            print(
                json.dumps(
                    {
                        "collection_success": result.get("collection_success"),
                        "collection_failed": result.get("collection_failed"),
                        "elapsed_sec": result.get("elapsed_sec"),
                    },
                    indent=2,
                ),
                flush=True,
            )
        except BiCacheRefreshError as exc:
            print(f"refresh finished with error (cache may still be written): {exc}", flush=True)

    payload = load_business_intelligence_data() or {}
    sellers = list(payload.get("sellers") or [])
    # Align seller list to approved mappings so missing collects are reported.
    by_id = {
        str(r.get("shop_id") or ""): r
        for r in sellers
        if isinstance(r, dict) and str(r.get("shop_id") or "")
    }
    aligned: list[dict] = []
    for row in approved:
        sid = str(row.get("shop_id") or "")
        if sid in by_id:
            aligned.append(by_id[sid])
        else:
            aligned.append(
                {
                    "shop_id": sid,
                    "shop_name": row.get("shop_name"),
                    "fastmoss_shop_id": row.get("fastmoss_shop_id"),
                    "fastmoss_shop_url": (
                        f"https://www.fastmoss.com/shop-marketing/detail/{row.get('fastmoss_shop_id')}"
                        if row.get("fastmoss_shop_id")
                        else None
                    ),
                    "status": "FETCH_FAILED",
                    "error": "Not present in BI cache after refresh",
                    "data_date": today.isoformat(),
                    "tiktok_mtd_adgmv_php": None,
                    "tiktok_m1_adgmv_php": None,
                }
            )

    report = validate_bi_sellers(aligned, today=today, periods=periods)
    print("\n" + format_validation_summary(report), flush=True)

    out = ROOT / "data" / "fastmoss_bi_validation_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {out}", flush=True)

    if report["all_success"]:
        # Refresh seed only when every shop is a fresh success.
        save_business_intelligence_data(payload)
        seed = ROOT / "business_intelligence_data.seed.json"
        seed.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Seed updated (all fresh success): {seed}", flush=True)
        return 0

    print(
        f"\nNOT claiming {report['total_shops']}/{report['total_shops']} successfully fetched — "
        f"{report['success_label']}, {report['failed_label']}",
        flush=True,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
