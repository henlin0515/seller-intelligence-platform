"""Auth and API exposure checks — run: python scripts/test_auth_security.py"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Minimal auth env for TestClient (force — local .env must not override tests)
os.environ["AUTH_USERNAME"] = "testuser"
os.environ["AUTH_PASSWORD"] = "testpass"
os.environ["AUTH_SESSION_SECRET"] = "test-session-secret-32chars-minimum!!"
os.environ["AUTH_COOKIE_SECURE"] = "false"
os.environ["AUTH_ALLOW_DEV_DEFAULTS"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

FORBIDDEN_STATUS_KEYS = {
    "spreadsheet_id",
    "spreadsheet_title",
    "data_source",
    "live_sheets_configured",
    "tabs_discovered",
    "tabs_merged",
    "error",
    "service_account_email",
    "layout",
    "merge_strategy",
}


def main() -> int:
    client = TestClient(app)
    errors: list[str] = []

    r = client.get("/api/seller/status")
    if r.status_code != 401:
        errors.append(f"GET /api/seller/status expected 401, got {r.status_code}")

    r = client.get("/", follow_redirects=False)
    if r.status_code not in (303, 307, 302) or "/login" not in (r.headers.get("location") or ""):
        errors.append(f"GET / unauthenticated expected redirect to login, got {r.status_code}")

    r = client.get("/static/index.html", follow_redirects=False)
    loc = r.headers.get("location") or ""
    if r.status_code not in (303, 302, 307) or "/login" not in loc:
        errors.append(
            f"GET /static/index.html expected redirect to login, got {r.status_code} {loc!r}"
        )

    r = client.get("/login")
    if r.status_code != 200:
        errors.append(f"GET /login expected 200, got {r.status_code}")

    r = client.get("/api/seller/debug/123")
    if r.status_code != 401:
        errors.append(f"GET /api/seller/debug unauthenticated expected 401, got {r.status_code}")

    login = client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "testpass"},
    )
    if login.status_code != 200:
        errors.append(f"login failed: {login.status_code} {login.text[:200]}")
    else:
        r = client.get("/api/seller/status")
        if r.status_code != 200:
            errors.append(f"authenticated status failed: {r.status_code}")
        else:
            body = r.json()
            leaked = FORBIDDEN_STATUS_KEYS.intersection(body.keys())
            if leaked:
                errors.append(f"status leaks internal keys: {sorted(leaked)}")

        r = client.get("/api/seller/debug/999999")
        if r.status_code != 404:
            errors.append(
                f"debug endpoint should be 404 when disabled, got {r.status_code}"
            )

    robots = client.get("/robots.txt")
    if robots.status_code != 200 or "Disallow: /" not in robots.text:
        errors.append("robots.txt missing or incorrect")

    if errors:
        print("FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("OK: auth security checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
