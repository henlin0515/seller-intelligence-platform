"""
Service Account authentication for Google Sheets API.

Supports:
- Local: JSON key file via GOOGLE_SHEETS_CREDENTIALS_PATH
- Railway: full JSON in GOOGLE_SHEETS_CREDENTIALS_JSON (no file on disk)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from seller.google_sheets.config import GoogleSheetsSettings, get_settings
from seller.google_sheets.paths import get_project_root, resolve_credentials_path
from seller.google_sheets.exceptions import (
    GoogleSheetsAuthError,
    GoogleSheetsNotConfiguredError,
)

try:
    from google.oauth2 import service_account
except ImportError:  # pragma: no cover - optional until deps installed
    service_account = None  # type: ignore[assignment]


def credentials_source_label(settings: GoogleSheetsSettings | None = None) -> str:
    """Non-secret label for logs/UI: local_path | env_json | none."""
    del settings  # use live env via get_credentials_source()
    from seller.google_sheets.config import get_credentials_source

    return get_credentials_source()


def _load_json_dict(settings: GoogleSheetsSettings) -> dict[str, Any]:
    if settings.has_credentials_json:
        try:
            return json.loads(settings.credentials_json)
        except json.JSONDecodeError as exc:
            raise GoogleSheetsAuthError(
                "GOOGLE_SHEETS_CREDENTIALS_JSON is not valid JSON."
            ) from exc

    path = resolve_credentials_path(settings.credentials_path)
    if not path.is_file():
        raise GoogleSheetsAuthError(
            f"Credentials file not found: {path} "
            f"(GOOGLE_SHEETS_CREDENTIALS_PATH={settings.credentials_path!r}, "
            f"project_root={get_project_root()})."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GoogleSheetsAuthError(f"Credentials file is not valid JSON: {path}") from exc


def build_credentials(settings: GoogleSheetsSettings | None = None):
    """
    Build google.oauth2.service_account.Credentials for configured scopes.

    Raises GoogleSheetsNotConfiguredError if settings are incomplete.
    Raises GoogleSheetsAuthError if the library is missing or JSON is invalid.
    """
    if service_account is None:
        raise GoogleSheetsAuthError(
            "google-auth is not installed. Run: pip install google-auth"
        )

    from seller.google_sheets.config import is_credentials_usable

    s = settings or get_settings()
    if not is_credentials_usable():
        raise GoogleSheetsNotConfiguredError(
            "Service Account credentials are not configured. "
            "See GOOGLE_SHEETS_SETUP.md."
        )

    info = _load_json_dict(s)
    if info.get("type") != "service_account":
        raise GoogleSheetsAuthError(
            'Credentials JSON must be a Service Account key (type: "service_account").'
        )

    try:
        return service_account.Credentials.from_service_account_info(
            info,
            scopes=list(s.scopes),
        )
    except Exception as exc:
        raise GoogleSheetsAuthError(
            f"Failed to build Service Account credentials: {exc}"
        ) from exc


def service_account_email(settings: GoogleSheetsSettings | None = None) -> str | None:
    """client_email from the key file — share the mirror sheet with this address."""
    from seller.google_sheets.config import is_credentials_usable

    s = settings or get_settings()
    if not is_credentials_usable():
        return None
    try:
        info = _load_json_dict(s)
        return info.get("client_email")
    except GoogleSheetsAuthError:
        return None
