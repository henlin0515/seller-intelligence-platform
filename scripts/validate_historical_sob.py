#!/usr/bin/env python3
"""Validate Historical SOB endpoint — Historical SOB module only."""
from __future__ import annotations

import json
import sys
import traceback
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")


def fetch_local_payload() -> tuple[int, dict | None, str | None]:
    try:
        from seller.intelligence.historical_sob import get_historical_sob_payload

        payload = get_historical_sob_payload(ensure_tiktok_cache=False)
        status = 200 if payload.get("status") in {"ok", "degraded"} else 500
        return status, payload, None
    except Exception as exc:
        return 500, None, traceback.format_exc()


def fetch_http_payload() -> tuple[int, dict | None, str | None]:
    req = urllib.request.Request(
        f"{BASE}/api/intelligence/v1/historical-sob",
        headers={"Accept": "application/json", "User-Agent": "validate-historical-sob/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, json.loads(body), None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {"detail": body[:500]}
        return exc.code, data, None
    except Exception as exc:
        return 0, None, traceback.format_exc()


def main() -> int:
    use_http = BASE.startswith("http")
    if sys.argv[1:2] == ["local"]:
        status, payload, err = fetch_local_payload()
    elif use_http:
        status, payload, err = fetch_http_payload()
    else:
        status, payload, err = fetch_local_payload()

    report: dict = {
        "api_status": status,
        "api_ok": status == 200,
        "error": err,
        "files_modified": [
            "seller/intelligence/historical_sob/ytd_monthly.py",
            "seller/intelligence/historical_sob/service.py",
            "seller/intelligence/router.py",
            "static/historical-sob.js",
            "static/intelligence-v1.css",
            "tests/test_historical_sob.py",
            "scripts/validate_historical_sob.py",
        ],
    }

    if payload:
        summary = payload.get("summary") or {}
        report.update(
            {
                "module_status": payload.get("status"),
                "warnings": payload.get("warnings") or [],
                "total_master_shops_loaded": summary.get("master_seller_count"),
                "ytd_monthly_rows_loaded": summary.get("ytd_monthly_rows_loaded"),
                "ytd_matched_count": summary.get("ytd_matched_count"),
                "ytd_unmatched_count": summary.get("ytd_unmatched_count"),
                "ytd_load_error": summary.get("ytd_load_error"),
                "april_shopee_gmv_total": summary.get("april_shopee_gmv_total"),
                "may_shopee_gmv_total": summary.get("may_shopee_gmv_total"),
                "april_tiktok_gmv_total": summary.get("april_tiktok_gmv_total"),
                "may_tiktok_gmv_total": summary.get("may_tiktok_gmv_total"),
                "tiktok_april_gmv_fetched_count": summary.get("tiktok_april_gmv_fetched_count"),
                "tiktok_may_gmv_fetched_count": summary.get("tiktok_may_gmv_fetched_count"),
                "first_10_rows": (payload.get("sellers") or [])[:10],
                "na_preview": payload.get("na_preview") or [],
            }
        )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if status == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
