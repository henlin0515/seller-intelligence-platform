"""
Environment-driven configuration for Google Sheets (mirror sheet).

No credentials are hardcoded. Load from .env via python-dotenv (app startup).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

DEFAULT_SCOPES = "https://www.googleapis.com/auth/spreadsheets.readonly"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_str(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


@dataclass(frozen=True)
class GoogleSheetsSettings:
    """Resolved settings for Service Account access to the mirror spreadsheet."""

    enabled: bool
    spreadsheet_id: str
    credentials_path: str
    credentials_json: str
    scopes: tuple[str, ...]
    primary_tab_hint: str
    connect_on_startup: bool

    @property
    def has_spreadsheet_id(self) -> bool:
        return bool(self.spreadsheet_id)

    @property
    def has_credentials_path(self) -> bool:
        return bool(self.credentials_path)

    @property
    def has_credentials_json(self) -> bool:
        return bool(self.credentials_json)

    def credentials_configured(self) -> bool:
        return self.has_credentials_path or self.has_credentials_json


@lru_cache(maxsize=1)
def get_settings() -> GoogleSheetsSettings:
    scopes_raw = _env_str("GOOGLE_SHEETS_SCOPES", DEFAULT_SCOPES)
    scopes = tuple(s.strip() for s in scopes_raw.split(",") if s.strip())
    return GoogleSheetsSettings(
        enabled=_env_bool("GOOGLE_SHEETS_ENABLED", False),
        spreadsheet_id=_env_str("GOOGLE_SHEET_MIRROR_ID"),
        credentials_path=_env_str("GOOGLE_SHEETS_CREDENTIALS_PATH"),
        credentials_json=_env_str("GOOGLE_SHEETS_CREDENTIALS_JSON"),
        scopes=scopes or (DEFAULT_SCOPES,),
        primary_tab_hint=_env_str("GOOGLE_SHEET_PRIMARY_TAB", "AI DATA"),
        connect_on_startup=_env_bool("GOOGLE_SHEETS_CONNECT_ON_STARTUP", False),
    )


def is_configured() -> bool:
    """True when enabled and spreadsheet id + credentials are present."""
    s = get_settings()
    return s.enabled and s.has_spreadsheet_id and s.credentials_configured()


def validate_for_connection() -> list[str]:
    """
    Return human-readable configuration errors (empty if ready to connect later).
    Does not call Google APIs.
    """
    s = get_settings()
    issues: list[str] = []
    if not s.enabled:
        issues.append("GOOGLE_SHEETS_ENABLED is not true (integration stays on mock data).")
    if not s.has_spreadsheet_id:
        issues.append("GOOGLE_SHEET_MIRROR_ID is missing.")
    if not s.credentials_configured():
        issues.append(
            "Set GOOGLE_SHEETS_CREDENTIALS_PATH (local file) or "
            "GOOGLE_SHEETS_CREDENTIALS_JSON (inline JSON for Railway)."
        )
    if s.has_credentials_path and s.has_credentials_json:
        issues.append(
            "Both credentials path and inline JSON are set; inline JSON will be used."
        )
    return issues
