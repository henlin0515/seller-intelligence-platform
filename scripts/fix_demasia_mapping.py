#!/usr/bin/env python3
"""Re-map Demasia (201629115) from sheet + FastMoss, update local + production."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from seller.fastmoss.mapping import (  # noqa: E402
    load_fastmoss_mapping,
    map_seller_to_fastmoss,
    save_fastmoss_mapping,
)
from seller.fastmoss.review import apply_manual_mapping_override  # noqa: E402
from seller.intelligence.seller_master import get_seller_master  # noqa: E402

SHOP_ID = "201629115"
BASE = os.environ.get("SIP_BASE_URL", "https://sellerintelligence.up.railway.app").rstrip("/")
USER = os.environ.get("AUTH_USERNAME", "Yilun")
PASSWORD = os.environ.get("AUTH_PASSWORD") or os.environ.get("ZWB_TEST_PASSWORD", "")


def login() -> urllib.request.OpenerDirector:
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    body = json.dumps({"username": USER, "password": PASSWORD}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener.open(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    if not data.get("authenticated"):
        raise RuntimeError("Production login failed")
    return opener


def api_json(opener: urllib.request.OpenerDirector, path: str, *, method: str = "GET", data: bytes | None = None) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method=method,
    )
    with opener.open(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def update_local(seller, mapped: dict) -> dict:
    payload = load_fastmoss_mapping()
    rows = payload.get("mappings") or []
    merged = {**mapped, "tiktok_shop_name": seller.tiktok_shop_name}
    found = False
    for i, row in enumerate(rows):
        if str(row.get("shop_id")) == SHOP_ID:
            rows[i] = {**row, **merged}
            found = True
            break
    if not found:
        rows.append(merged)
    payload["mappings"] = rows
    save_fastmoss_mapping(payload)
    return apply_manual_mapping_override(
        SHOP_ID,
        tiktok_shop_name=seller.tiktok_shop_name,
        fastmoss_shop_id=str(mapped["fastmoss_shop_id"]),
        fastmoss_shop_name=str(mapped["fastmoss_shop_name"]),
        fastmoss_shop_url=str(mapped["fastmoss_shop_url"]),
        confidence=float(mapped.get("confidence") or 1.0),
        notes="Re-mapped from sheet Demasia.ph + FastMoss search",
    )


def run_production_refresh(opener: urllib.request.OpenerDirector) -> None:
    api_json(opener, "/api/intelligence/v1/business/refresh-data", method="POST", data=b"{}")
    deadline = time.time() + 600
    while time.time() < deadline:
        time.sleep(5)
        st = api_json(opener, "/api/intelligence/v1/business/refresh-status")
        print(
            f"  {st.get('percent', 0):.0f}% {st.get('step_label')} "
            f"processed={st.get('shops_processed')}/{st.get('shops_total')}"
        )
        if not st.get("running"):
            if st.get("error"):
                raise RuntimeError(st["error"])
            return
    raise TimeoutError("Production refresh timed out")


def force_select(opener: urllib.request.OpenerDirector, mapped: dict) -> dict:
    qs = urllib.parse.urlencode(
        {
            "fastmoss_shop_id": mapped["fastmoss_shop_id"],
            "fastmoss_shop_name": mapped["fastmoss_shop_name"],
            "fastmoss_shop_url": mapped["fastmoss_shop_url"],
            "confidence": mapped.get("confidence", 1.0),
            "notes": "Manual fix: Demasia.ph from FastMoss after sheet update",
        }
    )
    return api_json(
        opener,
        f"/api/intelligence/v1/mapping-review/{SHOP_ID}/select?{qs}",
        method="POST",
        data=b"",
    )


def print_production_row(opener: urllib.request.OpenerDirector) -> None:
    mr = api_json(opener, "/api/intelligence/v1/mapping-review")
    for row in mr.get("rows") or []:
        if str(row.get("shop_id")) == SHOP_ID:
            print(
                "Production:",
                json.dumps(
                    {
                        "shop_name": row.get("shop_name"),
                        "tiktok": row.get("tiktok_shop_name"),
                        "fastmoss": row.get("fastmoss_shop_name"),
                        "fastmoss_id": row.get("fastmoss_shop_id"),
                        "review": row.get("review_status"),
                        "audit": row.get("audit_status"),
                    },
                    ensure_ascii=False,
                ),
            )
            return
    print("Production: shop not found in mapping review")


def main() -> int:
    master = get_seller_master(force_refresh=True)
    seller = next(s for s in master.sellers if s.shop_id == SHOP_ID)
    print("Sheet:", json.dumps(seller.as_dict(), ensure_ascii=False))

    mapped = map_seller_to_fastmoss(seller)
    print("FastMoss:", mapped.get("fastmoss_shop_name"), mapped.get("fastmoss_shop_id"), mapped.get("mapping_status"))
    if mapped.get("mapping_status") != "MAPPED":
        print("FAIL: FastMoss search did not find Demasia.ph")
        return 1

    local = update_local(seller, mapped)
    print("Local review:", local.get("review_status"), local.get("audit_status"))

    try:
        opener = login()
        print("Production login OK")
    except Exception as exc:
        print(f"SKIP production (login failed): {exc}")
        return 0

    print("Running production Update Data (sheet reload + remap + historical)...")
    run_production_refresh(opener)

    mr = api_json(opener, "/api/intelligence/v1/mapping-review")
    row = next((r for r in (mr.get("rows") or []) if str(r.get("shop_id")) == SHOP_ID), None)
    needs_fix = (
        not row
        or row.get("fastmoss_shop_name") != mapped["fastmoss_shop_name"]
        or row.get("review_status") != "APPROVED"
    )
    if needs_fix:
        print("Applying production select for Demasia.ph...")
        force_select(opener, mapped)

    print_production_row(opener)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
