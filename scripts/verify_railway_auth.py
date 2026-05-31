"""Verify Railway deploy exposes login-only surface for anonymous users."""
from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request

BASE_URLS = [
    "https://seller-intelligence-platform-production.up.railway.app",
    "https://seller-intelligence-platform.up.railway.app",
]


def fetch(url: str, *, method: str = "GET") -> tuple[int, dict[str, str], str]:
    req = urllib.request.Request(
        url, method=method, headers={"User-Agent": "ShopeeAI-auth-verify/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, headers, resp.read(8000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        headers = {k.lower(): v for k, v in exc.headers.items()}
        body = exc.read(8000).decode("utf-8", "replace") if exc.fp else ""
        return exc.code, headers, body


def check(base: str) -> dict[str, object]:
    status_code, _, _ = fetch(f"{base}/api/seller/status")
    home_code, home_headers, home_body = fetch(f"{base}/")
    login_code, _, login_body = fetch(f"{base}/login")
    static_code, static_headers, _ = fetch(f"{base}/static/index.html")
    loc = home_headers.get("location", "")
    static_loc = static_headers.get("location", "")
    return {
        "base": base,
        "api_status": status_code,
        "home_code": home_code,
        "home_login_redirect": "/login" in loc,
        "login_ok": login_code == 200 and "loginForm" in login_body,
        "static_blocked": static_code in (303, 302, 307) and "/login" in static_loc,
        "ok": status_code == 401
        and home_code in (303, 302, 307)
        and "/login" in loc
        and login_code == 200
        and "loginForm" in login_body,
    }


def main() -> int:
    deadline = time.time() + 180
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        print(f"\n--- attempt {attempt} ---")
        results = [check(b) for b in BASE_URLS]
        for r in results:
            print(
                f"{r['base']}: api={r['api_status']} home={r['home_code']} "
                f"login_ok={r['login_ok']} static_blocked={r['static_blocked']}"
            )
        if any(r["ok"] for r in results):
            print("\nOK: at least one Railway URL passes auth surface checks")
            return 0
        time.sleep(20)
    print("\nFAILED: no Railway URL passed checks within timeout")
    return 1


if __name__ == "__main__":
    sys.exit(main())
