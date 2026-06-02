#!/usr/bin/env python3
"""Smoke test POST /api/intelligence/v1/refresh-sheets."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

BASE = os.environ.get("SIP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USER = os.environ.get("AUTH_USERNAME", "admin")
PASSWORD = os.environ.get("AUTH_PASSWORD", "")


def login() -> str | None:
    if not PASSWORD:
        print("SKIP: set AUTH_PASSWORD to test authenticated endpoint")
        return None
    payload = json.dumps({"username": USER, "password": PASSWORD}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data.get("access_token")


def post_refresh(token: str) -> dict:
    req = urllib.request.Request(
        f"{BASE}/api/intelligence/v1/refresh-sheets",
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    token = login()
    if not token:
        return 0
    try:
        result = post_refresh(token)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        print(f"HTTP {exc.code}: {body[:500]}")
        return 1
    required = ("success", "refreshed_at", "seller_count", "ai_data_count", "shopee_adgmv_count")
    missing = [k for k in required if k not in result]
    if missing:
        print("Missing keys:", missing, result)
        return 1
    if not result.get("success"):
        print("success=false", result)
        return 1
    print("REFRESH_OK")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
