"""Tests for multi-user authentication."""

from __future__ import annotations

import json
from pathlib import Path

from seller.auth.passwords import hash_password, verify_password
from seller.auth.users import ROLE_STANDARD, authenticate, clear_auth_users_cache, list_auth_users


def test_hash_and_verify_password():
    stored = hash_password("Secret@2026")
    assert verify_password("Secret@2026", stored)
    assert not verify_password("wrong", stored)


def test_authenticate_standard_users(tmp_path, monkeypatch):
    users_path = tmp_path / "auth_users.json"
    users_path.write_text(
        json.dumps(
            [
                {
                    "username": "Yilun",
                    "password_hash": hash_password("Yilun@2026"),
                    "role": "standard_user",
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTH_USERNAME", "admin")
    monkeypatch.setenv("AUTH_PASSWORD", "adminpass")
    monkeypatch.setenv("AUTH_USERS_PATH", str(users_path))
    clear_auth_users_cache()

    admin = authenticate("admin", "adminpass")
    assert admin is not None
    assert admin.role == "admin"

    user = authenticate("Yilun", "Yilun@2026")
    assert user is not None
    assert user.role == ROLE_STANDARD

    assert authenticate("Yilun", "bad") is None
    clear_auth_users_cache()


def test_config_auth_users_file_has_seven_standard_users():
    path = Path(__file__).resolve().parents[1] / "config" / "auth_users.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert len(rows) == 7
    assert all(row.get("role") == ROLE_STANDARD for row in rows)
    assert all(row.get("password_hash", "").startswith("pbkdf2_sha256$") for row in rows)
