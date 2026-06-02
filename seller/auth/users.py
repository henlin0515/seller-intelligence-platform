"""Application users — env admin plus hashed standard users from config file."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from seller.auth.config import get_auth_settings
from seller.auth.passwords import verify_password

logger = logging.getLogger("auth.users")

DEFAULT_USERS_PATH = Path("config/auth_users.json")
ROLE_ADMIN = "admin"
ROLE_STANDARD = "standard_user"


@dataclass(frozen=True)
class AuthUser:
    username: str
    role: str
    source: str


def auth_users_path() -> Path:
    raw = (os.getenv("AUTH_USERS_PATH") or "").strip()
    return Path(raw) if raw else DEFAULT_USERS_PATH


@lru_cache(maxsize=1)
def _load_standard_users() -> dict[str, dict[str, str]]:
    path = auth_users_path()
    if not path.is_file():
        logger.warning("Auth users file not found: %s", path)
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to read auth users file %s: %s", path, exc)
        return {}

    users: dict[str, dict[str, str]] = {}
    rows = payload if isinstance(payload, list) else payload.get("users") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        username = str(row.get("username") or "").strip()
        password_hash = str(row.get("password_hash") or "").strip()
        if not username or not password_hash:
            continue
        role = str(row.get("role") or ROLE_STANDARD).strip() or ROLE_STANDARD
        users[username] = {
            "username": username,
            "password_hash": password_hash,
            "role": role,
        }
    return users


def list_auth_users() -> list[AuthUser]:
    settings = get_auth_settings()
    users: list[AuthUser] = []
    if settings.username:
        users.append(
            AuthUser(username=settings.username, role=ROLE_ADMIN, source="env_admin")
        )
    for row in _load_standard_users().values():
        users.append(
            AuthUser(
                username=row["username"],
                role=row.get("role") or ROLE_STANDARD,
                source="auth_users_file",
            )
        )
    return users


def authenticate(username: str, password: str) -> AuthUser | None:
    """Validate credentials against env admin and configured standard users."""
    import hmac as _hmac

    name = (username or "").strip()
    if not name or not password:
        return None

    settings = get_auth_settings()
    if settings.username and settings.password:
        if _hmac.compare_digest(name, settings.username) and _hmac.compare_digest(
            password, settings.password
        ):
            return AuthUser(username=settings.username, role=ROLE_ADMIN, source="env_admin")

    row = _load_standard_users().get(name)
    if row and verify_password(password, row["password_hash"]):
        return AuthUser(
            username=row["username"],
            role=row.get("role") or ROLE_STANDARD,
            source="auth_users_file",
        )
    return None


def clear_auth_users_cache() -> None:
    _load_standard_users.cache_clear()
