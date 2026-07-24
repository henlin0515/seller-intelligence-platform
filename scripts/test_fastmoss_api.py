#!/usr/bin/env python3
"""
Diagnostic: probe FastMoss recentData JSON API for one shop.

Usage:
  python scripts/test_fastmoss_api.py --shop-id=<FAST_MOSS_SHOP_ID>

Prints only: endpoint path, status code, response time, has_data, top-level keys.
Never prints Authorization, Cookie, API key, or full response body.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Probe FastMoss recentData (safe output)")
    parser.add_argument("--shop-id", required=True, help="FastMoss shop id")
    args = parser.parse_args()

    from seller.fastmoss.client import (
        RECENT_DATA_PATH,
        anonymous_session,
        base_url,
        mask_secrets,
        region,
        request_with_retry,
    )
    from seller.fastmoss.provider import RECENT_DATA_CURRENCY
    from seller.intelligence.business_time import business_today
    from seller.intelligence.periods import resolve_periods

    shop_id = str(args.shop_id).strip()
    periods = resolve_periods(business_today())
    url = f"{base_url()}{RECENT_DATA_PATH}"
    params = {
        "id": shop_id,
        "start_date": periods.mtd.start.isoformat(),
        "end_date": periods.mtd.end.isoformat(),
        "region": region(),
        "_time": str(int(time.time())),
        "cnonce": "10000001",
    }

    started = time.perf_counter()
    try:
        resp = request_with_retry(
            anonymous_session(),
            "GET",
            url,
            params=params,
            headers={"Referer": f"{base_url()}/shop-marketing/detail/{shop_id}"},
            raise_for_status=False,
            retries=2,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        try:
            payload = resp.json()
        except Exception:
            payload = {}
        keys = sorted(payload.keys()) if isinstance(payload, dict) else []
        data = payload.get("data") if isinstance(payload, dict) else None
        info = {}
        if isinstance(data, dict):
            lst = data.get("list") or {}
            if isinstance(lst, dict):
                info = lst.get("total_info") or {}
        has_data = bool(
            isinstance(info, dict) and info.get("sale_amount") is not None
        )
        print(
            "\n".join(
                [
                    f"endpoint_path={RECENT_DATA_PATH}",
                    f"status_code={resp.status_code}",
                    f"response_time_ms={elapsed_ms}",
                    f"has_data={has_data}",
                    f"currency_assumed={RECENT_DATA_CURRENCY}",
                    f"top_level_keys={keys}",
                    f"api_code={payload.get('code') if isinstance(payload, dict) else None}",
                    f"period={periods.mtd.start}..{periods.mtd.end}",
                ]
            )
        )
        return 0 if resp.status_code == 200 else 1
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        print(
            "\n".join(
                [
                    f"endpoint_path={RECENT_DATA_PATH}",
                    "status_code=0",
                    f"response_time_ms={elapsed_ms}",
                    "has_data=False",
                    f"error={mask_secrets(str(exc))}",
                ]
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
