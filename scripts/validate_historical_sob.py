#!/usr/bin/env python3
"""Validate Historical SOB module against live seller master + YTD sheet."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seller.intelligence.historical_sob import get_historical_sob_payload  # noqa: E402
from seller.intelligence.seller_master import get_seller_master  # noqa: E402


def main() -> int:
    master = get_seller_master()
    payload = get_historical_sob_payload(master, ensure_tiktok_cache=False)
    summary = payload.get("summary") or {}
    rows = payload.get("sellers") or []
    sample = rows[:10]

    report = {
        "master_seller_count": summary.get("master_seller_count"),
        "ytd_monthly_rows_loaded": summary.get("ytd_monthly_rows_loaded"),
        "tiktok_historical_fetched_count": summary.get("tiktok_historical_fetched_count"),
        "april_sob_calculated_count": summary.get("april_sob_calculated_count"),
        "may_sob_calculated_count": summary.get("may_sob_calculated_count"),
        "first_10_rows": sample,
        "files_modified": [
            "seller/intelligence/historical_sob/__init__.py",
            "seller/intelligence/historical_sob/ytd_monthly.py",
            "seller/intelligence/historical_sob/store.py",
            "seller/intelligence/historical_sob/collector.py",
            "seller/intelligence/historical_sob/portfolio.py",
            "seller/intelligence/historical_sob/service.py",
            "seller/intelligence/router.py",
            "seller/intelligence/refresh_data.py",
            "static/historical-sob.js",
            "static/index.html",
            "static/platform.js",
            "static/intelligence-v1.css",
            "static/i18n.js",
            "tests/test_historical_sob.py",
            ".env.example",
        ],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))

    ok = (
        int(summary.get("master_seller_count") or 0) >= 5
        and int(summary.get("ytd_monthly_rows_loaded") or 0) >= 1
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
