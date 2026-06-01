"""Smoke test Seller Intelligence V1 API routes."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["AUTH_USERNAME"] = "testuser"
os.environ["AUTH_PASSWORD"] = "testpass"
os.environ["AUTH_SESSION_SECRET"] = "test-session-secret-32chars-minimum!!"
os.environ["AUTH_COOKIE_SECURE"] = "false"
os.environ["AUTH_ALLOW_DEV_DEFAULTS"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

ROUTES = [
    "/api/intelligence/v1",
    "/api/intelligence/v1/dashboard",
    "/api/intelligence/v1/business",
    "/api/intelligence/v1/assortment",
    "/api/intelligence/v1/voucher",
]


def main() -> int:
    client = TestClient(app)
    errors = []

    for path in ROUTES:
        r = client.get(path)
        if r.status_code != 401:
            errors.append(f"{path} unauthenticated expected 401 got {r.status_code}")

    login = client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "testpass"},
    )
    if login.status_code != 200:
        errors.append(f"login failed {login.status_code}")
        return 1

    for path in ROUTES:
        r = client.get(path)
        if r.status_code != 200:
            errors.append(f"{path} authenticated expected 200 got {r.status_code}")
        elif path.endswith("/business"):
            body = r.json()
            if not body.get("sellers"):
                errors.append(f"{path} missing sellers")

    if errors:
        print("FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("OK: intelligence v1 API routes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
