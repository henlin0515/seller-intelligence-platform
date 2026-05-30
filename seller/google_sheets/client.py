"""
Google Sheets API client (Service Account).

Placeholder: authenticates when configured but does not load mirror data until
the live connection phase is approved.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from seller.google_sheets.auth import build_credentials, service_account_email
from seller.google_sheets.config import GoogleSheetsSettings, get_settings, is_configured
from seller.google_sheets.exceptions import (
    GoogleSheetsNotConfiguredError,
    GoogleSheetsNotEnabledError,
)

logger = logging.getLogger("seller.google_sheets")

try:
    import gspread
except ImportError:  # pragma: no cover
    gspread = None  # type: ignore[assignment]


class GoogleSheetsClient:
    """
    Thin wrapper around gspread for the mirror spreadsheet.

    Future methods (not wired to dashboard yet):
    - list_worksheet_titles()
    - fetch_worksheet_as_rows(title)
    - fetch_all_tabs()
    """

    def __init__(self, settings: GoogleSheetsSettings, gc: Any, spreadsheet: Any):
        self._settings = settings
        self._gc = gc
        self._spreadsheet = spreadsheet

    @property
    def spreadsheet_id(self) -> str:
        return self._settings.spreadsheet_id

    @property
    def service_account_email(self) -> str | None:
        return service_account_email(self._settings)

    def ping(self) -> dict[str, Any]:
        """
        Verify auth + spreadsheet access (for manual checks after setup).
        Returns spreadsheet title and worksheet names — no seller data merge.
        """
        titles = [ws.title for ws in self._spreadsheet.worksheets()]
        return {
            "spreadsheet_id": self.spreadsheet_id,
            "spreadsheet_title": self._spreadsheet.title,
            "worksheet_titles": titles,
            "worksheet_count": len(titles),
            "service_account_email": self.service_account_email,
        }

    def list_worksheet_titles(self) -> list[str]:
        """Tab discovery (used in a later phase)."""
        return [ws.title for ws in self._spreadsheet.worksheets()]

    def fetch_worksheet_values(self, title: str) -> list[list[Any]]:
        """Raw grid for one tab."""
        worksheet = self._spreadsheet.worksheet(title)
        return worksheet.get_all_values()

    def fetch_all_tab_grids(self) -> dict[str, list[list[Any]]]:
        """All worksheet grids keyed by tab title."""
        return {title: self.fetch_worksheet_values(title) for title in self.list_worksheet_titles()}


def _require_gspread() -> None:
    if gspread is None:
        raise GoogleSheetsNotConfiguredError(
            "gspread is not installed. Run: pip install gspread google-auth"
        )


@lru_cache(maxsize=1)
def get_sheets_client() -> GoogleSheetsClient:
    """
    Singleton client. Cached after first successful auth.

    Raises if GOOGLE_SHEETS_ENABLED is false or configuration is incomplete.
    """
    settings = get_settings()
    if not settings.enabled:
        raise GoogleSheetsNotEnabledError(
            "Google Sheets integration is disabled. Set GOOGLE_SHEETS_ENABLED=true "
            "after completing GOOGLE_SHEETS_SETUP.md."
        )
    if not is_configured():
        raise GoogleSheetsNotConfiguredError(
            "Google Sheets is not fully configured. See validate_for_connection() "
            "and GOOGLE_SHEETS_SETUP.md."
        )

    _require_gspread()
    creds = build_credentials(settings)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(settings.spreadsheet_id)
    logger.info(
        "Google Sheets client ready for spreadsheet %s (auth=%s)",
        settings.spreadsheet_id,
        "configured",
    )
    return GoogleSheetsClient(settings, gc, spreadsheet)


def try_get_sheets_client() -> GoogleSheetsClient | None:
    """Return client when configured and enabled; otherwise None (no exception)."""
    try:
        return get_sheets_client()
    except Exception:
        return None
