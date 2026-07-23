#!/usr/bin/env python3
"""Backfill Historical SOB May/June TikTok GMV for all MAPPED FastMoss shops."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    from seller.intelligence.historical_sob.service import refresh_historical_sob_tiktok_cache
    from seller.intelligence.historical_sob.store import load_historical_sob_cache

    print("Refreshing May/June TikTok GMV for mapped shops…", flush=True)
    result = refresh_historical_sob_tiktok_cache(None, delay_sec=0.8, force=True)
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    cache = load_historical_sob_cache()
    shops = cache.get("shops") or {}
    ok = sum(1 for r in shops.values() if isinstance(r, dict) and r.get("status") == "success")
    print(f"cache_shops={len(shops)} success={ok} updated_at={cache.get('updated_at')}", flush=True)
    return 0 if result.get("failed_count", 0) == 0 or ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
