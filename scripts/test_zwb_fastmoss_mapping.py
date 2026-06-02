#!/usr/bin/env python3
"""Validate ZWB.PH FastMoss mapping via search + optional live refresh."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from seller.fastmoss.mapping import (  # noqa: E402
    MAPPING_MAPPED,
    map_seller_to_fastmoss,
)
from seller.fastmoss.search import search_shops  # noqa: E402
from seller.intelligence.seller_master import SellerMasterRecord  # noqa: E402

TARGET_SHOP = os.environ.get("ZWB_SHOP_NAME", "ZWB.PH")
TARGET_TIKTOK = os.environ.get("ZWB_TIKTOK_NAME", "FS.STORE23")
BASE = os.environ.get("SIP_BASE_URL", "https://sellerintelligence.up.railway.app").rstrip("/")
USER = os.environ.get("AUTH_USERNAME", "Yilun")
PASSWORD = os.environ.get("ZWB_TEST_PASSWORD", "Yilun@2026")


def login() -> urllib.request.OpenerDirector:
    import http.cookiejar

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    payload = json.dumps({"username": USER, "password": PASSWORD}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener.open(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    if not data.get("authenticated"):
        raise RuntimeError(f"login failed for {USER}")
    return opener


def main() -> int:
    print(f"=== FastMoss search for {TARGET_TIKTOK!r} ===")
    candidates = search_shops(TARGET_TIKTOK)
    print(f"candidates: {len(candidates)}")
    for row in candidates[:5]:
        print(f"  - {row.get('fastmoss_shop_name')} ({row.get('fastmoss_shop_id')})")

    seller = SellerMasterRecord(
        shop_id="zwb-test",
        shop_name=TARGET_SHOP,
        shopee_link="",
        tiktok_shop_name=TARGET_TIKTOK,
    )
    mapped = map_seller_to_fastmoss(seller, candidates=candidates)
    print("\nLocal map result:")
    print(json.dumps(mapped, ensure_ascii=False, indent=2))
    if mapped.get("mapping_status") != MAPPING_MAPPED:
        print("FAIL: expected MAPPED from local search")
        return 1

    print(f"\n=== Live refresh on {BASE} ===")
    try:
        opener = login()
    except Exception as exc:
        print(f"SKIP live refresh: {exc}")
        return 0

    req = urllib.request.Request(
        f"{BASE}/api/intelligence/v1/refresh-fastmoss-mapping",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener.open(req, timeout=300) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode()[:500]}")
        return 1

    print(json.dumps(result, indent=2))

    req2 = urllib.request.Request(f"{BASE}/api/intelligence/v1/business")
    with opener.open(req2, timeout=120) as resp:
        business = json.loads(resp.read().decode())

    zwb = next(
        (
            s
            for s in business.get("sellers") or []
            if TARGET_SHOP.lower() in str(s.get("shop_name") or "").lower()
            or "zwb" in str(s.get("shop_name") or "").lower()
        ),
        None,
    )
    print("\nZWB row after refresh:")
    if not zwb:
        print(f"Shop {TARGET_SHOP!r} not found in business payload")
        return 1
    print(json.dumps(zwb, ensure_ascii=False, indent=2))
    status = str(zwb.get("fastmoss_match_status") or "").upper()
    if status != MAPPING_MAPPED:
        print(f"FAIL: expected MAPPED, got {status}")
        return 1
    print("PASS: ZWB.PH is MAPPED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
