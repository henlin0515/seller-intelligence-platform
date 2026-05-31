"""Auth configuration from environment only — never hardcode credentials."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthSettings:
    username: str
    password: str
    session_secret: str
    cookie_secure: bool
    session_cookie_name: str
    inactivity_seconds: int
    max_login_attempts: int
    lockout_seconds: int


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def get_auth_settings() -> AuthSettings:
    return AuthSettings(
        username=(os.getenv("AUTH_USERNAME") or "").strip(),
        password=os.getenv("AUTH_PASSWORD") or "",
        session_secret=(os.getenv("AUTH_SESSION_SECRET") or "").strip(),
        cookie_secure=_env_bool(
            "AUTH_COOKIE_SECURE",
            bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_SERVICE_ID")),
        ),
        session_cookie_name=(os.getenv("AUTH_SESSION_COOKIE") or "sip_session").strip(),
        inactivity_seconds=int(os.getenv("SESSION_INACTIVITY_MINUTES", "30")) * 60,
        max_login_attempts=int(os.getenv("AUTH_MAX_LOGIN_ATTEMPTS", "5")),
        lockout_seconds=int(os.getenv("AUTH_LOCKOUT_MINUTES", "30")) * 60,
    )


def validate_auth_config() -> None:
    """Fail fast at startup if auth is not configured."""
    s = get_auth_settings()
    missing = []
    if not s.username:
        missing.append("AUTH_USERNAME")
    if not s.password:
        missing.append("AUTH_PASSWORD")
    if not s.session_secret or len(s.session_secret) < 32:
        missing.append("AUTH_SESSION_SECRET (min 32 characters)")
    if missing:
        raise RuntimeError(
            "Authentication is required. Set in Railway environment variables: "
            + ", ".join(missing)
        )


def dev_session_secret() -> str:
    """Ephemeral secret for local development only when explicitly allowed."""
    if not _env_bool("AUTH_ALLOW_DEV_DEFAULTS", False):
        return ""
    return secrets.token_hex(32)
