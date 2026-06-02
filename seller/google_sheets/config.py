"""
Environment-driven configuration for Google Sheets (mirror sheet).

No credentials are hardcoded. Load from .env via python-dotenv (app startup).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("seller.google_sheets")

DEFAULT_SCOPES = "https://www.googleapis.com/auth/spreadsheets.readonly"

# Spreadsheet id env keys (Railway dashboards often use alternate names)
_SPREADSHEET_ID_KEYS = (
    "GOOGLE_SHEET_MIRROR_ID",
    "GOOGLE_SHEETS_MIRROR_ID",
    "GOOGLE_SPREADSHEET_ID",
)


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
        """Env presence only; use is_credentials_usable() for file/JSON validity."""
        return self.has_credentials_path or self.has_credentials_json


def _env_spreadsheet_id() -> str:
    for key in _SPREADSHEET_ID_KEYS:
        val = _env_str(key)
        if val:
            return val
    return ""


def _credentials_json_usable(raw: str) -> bool:
    text = (raw or "").strip()
    return len(text) > 20 and text.startswith("{")


def _credentials_path_usable(path: str) -> bool:
    """True only when the explicit env path points to a real file (no auto-discovery)."""
    raw = (path or "").strip()
    if not raw:
        return False
    from seller.google_sheets.paths import get_project_root

    root = get_project_root()
    p = Path(raw)
    resolved = p.resolve() if p.is_absolute() else (root / p).resolve()
    return resolved.is_file()


def get_credentials_source() -> str:
    """
    Where credentials will be loaded from: local_path | env_json | none.
    JSON env wins when both are usable (Railway).
    """
    s = get_settings()
    if _credentials_json_usable(s.credentials_json):
        return "env_json"
    if _credentials_path_usable(s.credentials_path):
        return "local_path"
    return "none"


def is_credentials_usable() -> bool:
    """True when inline JSON or an on-disk credentials file is available."""
    s = get_settings()
    if _credentials_json_usable(s.credentials_json):
        return True
    if s.has_credentials_path and _credentials_path_usable(s.credentials_path):
        return True
    return False


@lru_cache(maxsize=1)
def get_settings() -> GoogleSheetsSettings:
    scopes_raw = _env_str("GOOGLE_SHEETS_SCOPES", DEFAULT_SCOPES)
    scopes = tuple(s.strip() for s in scopes_raw.split(",") if s.strip())
    return GoogleSheetsSettings(
        enabled=_env_bool("GOOGLE_SHEETS_ENABLED", False),
        spreadsheet_id=_env_spreadsheet_id(),
        credentials_path=_env_str("GOOGLE_SHEETS_CREDENTIALS_PATH"),
        credentials_json=_env_str("GOOGLE_SHEETS_CREDENTIALS_JSON"),
        scopes=scopes or (DEFAULT_SCOPES,),
        primary_tab_hint=_env_str("GOOGLE_SHEET_PRIMARY_TAB", "AI data"),
        connect_on_startup=_env_bool("GOOGLE_SHEETS_CONNECT_ON_STARTUP", False),
    )


def clear_settings_cache() -> None:
    get_settings.cache_clear()


def is_configured() -> bool:
    """True when enabled, spreadsheet id set, and credentials JSON or file is usable."""
    s = get_settings()
    return s.enabled and s.has_spreadsheet_id and is_credentials_usable()


def log_startup_configuration() -> None:
    """Log Sheets env summary (no secrets). Call after load_dotenv on app startup."""
    s = get_settings()
    source = get_credentials_source()
    logger.info(
        "Google Sheets startup: GOOGLE_SHEETS_ENABLED=%s spreadsheet_id_set=%s "
        "credentials_source=%s configured=%s",
        os.getenv("GOOGLE_SHEETS_ENABLED", "(unset)"),
        bool(s.has_spreadsheet_id),
        source,
        is_configured(),
    )
    if not s.enabled:
        logger.warning(
            "Google Sheets disabled (GOOGLE_SHEETS_ENABLED is not true/1/yes/on)."
        )
    elif not s.has_spreadsheet_id:
        logger.warning(
            "Google Sheets missing spreadsheet id (set one of: %s).",
            ", ".join(_SPREADSHEET_ID_KEYS),
        )
    elif source == "none":
        logger.warning(
            "Google Sheets credentials missing: set GOOGLE_SHEETS_CREDENTIALS_JSON "
            "(Railway) or GOOGLE_SHEETS_CREDENTIALS_PATH to a file that exists (local)."
        )
    issues = validate_for_connection()
    if issues:
        logger.warning("Google Sheets configuration issues: %s", "; ".join(issues))


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
    if not is_credentials_usable():
        if s.has_credentials_path and not _credentials_path_usable(s.credentials_path):
            issues.append(
                "GOOGLE_SHEETS_CREDENTIALS_PATH is set but the file was not found on disk."
            )
        if s.has_credentials_json and not _credentials_json_usable(s.credentials_json):
            issues.append(
                "GOOGLE_SHEETS_CREDENTIALS_JSON is set but is empty or not valid JSON."
            )
        if not s.has_credentials_path and not s.has_credentials_json:
            issues.append(
                "Set GOOGLE_SHEETS_CREDENTIALS_PATH (local file) or "
                "GOOGLE_SHEETS_CREDENTIALS_JSON (inline JSON for Railway)."
            )
    elif s.has_credentials_path and s.has_credentials_json:
        issues.append(
            "Both credentials path and inline JSON are set; inline JSON will be used."
        )
    return issues
