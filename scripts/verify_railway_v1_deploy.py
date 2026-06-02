"""Verify Railway deploy: health, login, intelligence V1 routes."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE_URLS = [
    "https://sellerintelligence.up.railway.app",
    "https://seller-intelligence-platform-production.up.railway.app",
    "https://seller-intelligence-platform.up.railway.app",
]
TIMEOUT = 25
MAX_WAIT = 180


def fetch(url: str, *, method: str = "GET", data: bytes | None = None, headers: dict | None = None) -> tuple[int, str]:
    h = {"User-Agent": "ShopeeAI-v1-deploy/1.0"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read(12000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = exc.read(12000).decode("utf-8", "replace") if exc.fp else ""
        return exc.code, body
    except Exception as exc:
        return 0, str(exc)


def check(base: str) -> dict:
    health_s, _ = fetch(f"{base}/health")
    login_page_s, login_body = fetch(f"{base}/login")
    api_s, _ = fetch(f"{base}/api/intelligence/v1/business")
    static_s, static_body = fetch(f"{base}/static/intelligence-v1.js")
    home_s, _home_body = fetch(f"{base}/")
    if home_s in (301, 302, 303, 307):
        pass
    intel_js = "ShpIntelligenceV1" in static_body and "Shop View" in static_body
    login_ok = login_page_s == 200 and "loginForm" in login_body
    return {
        "base": base,
        "health": health_s,
        "login": login_page_s,
        "login_ok": login_ok,
        "api_unauth": api_s,
        "static_js": static_s,
        "intel_js": intel_js,
        "home": home_s,
        "ok": health_s == 200
        and login_ok
        and api_s == 401
        and static_s == 200
        and intel_js,
    }


def main() -> int:
    deadline = time.time() + MAX_WAIT
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        print(f"\n--- attempt {attempt} ---")
        results = [check(b) for b in BASE_URLS]
        for r in results:
            print(
                f"{r['base']}: health={r['health']} login={r['login']} "
                f"api={r['api_unauth']} static={r['static_js']} ok={r['ok']}"
            )
        live = [r for r in results if r["ok"]]
        if live:
            print("\nLIVE:", json.dumps(live[0], indent=2))
            return 0
        time.sleep(20)
    print("\nNo Railway URL passed checks (may still be deploying or service offline).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
