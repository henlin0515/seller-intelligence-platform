#!/usr/bin/env python3
"""Verify admin and standard user logins."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

os.environ.setdefault("AUTH_SESSION_SECRET", "local-test-session-secret-32chars-min!!")
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")
os.environ.setdefault("AUTH_ALLOW_DEV_DEFAULTS", "true")

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

STANDARD_USERS = [
    ("Yilun", "Yilun@2026"),
    ("Eric", "Eric@2026"),
    ("Kaiwen", "Kaiwen@2026"),
    ("Nikki", "Nikki@2026"),
    ("Lori", "Lori@2026"),
    ("Frida", "Frida@2026"),
    ("Paul", "Paul@2026"),
]


def main() -> int:
    admin_user = os.getenv("AUTH_USERNAME", "").strip()
    admin_pass = os.getenv("AUTH_PASSWORD", "")
    client = TestClient(app)
    results: list[tuple[str, str, bool, str]] = []

    def check(username: str, password: str) -> tuple[bool, str]:
        client.post("/api/auth/logout")
        login = client.post("/api/auth/login", json={"username": username, "password": password})
        if login.status_code != 200:
            return False, f"login {login.status_code}"
        body = login.json()
        me = client.get("/api/auth/me")
        me_body = me.json()
        role = me_body.get("role") or body.get("role")
        if not me_body.get("authenticated"):
            return False, "session not authenticated"
        if me_body.get("username") != username:
            return False, f"username mismatch {me_body.get('username')!r}"
        return True, str(role or "unknown")

    if admin_user and admin_pass:
        ok, detail = check(admin_user, admin_pass)
        results.append((admin_user, "admin", ok, detail))
    else:
        print("WARN: AUTH_USERNAME/AUTH_PASSWORD not set; skipping admin login test")

    for username, password in STANDARD_USERS:
        ok, detail = check(username, password)
        results.append((username, "standard_user", ok, detail))

    print("=== AUTH LOGIN TESTS ===")
    for username, expected_role, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"{status} {username} role={detail} (expected {expected_role})")

    total = 1 + len(STANDARD_USERS) if admin_user and admin_pass else len(STANDARD_USERS)
    passed = sum(1 for *_, ok, _ in results if ok)
    print(f"\nTotal users configured: {total}")
    print(f"Passed: {passed}/{len(results)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
