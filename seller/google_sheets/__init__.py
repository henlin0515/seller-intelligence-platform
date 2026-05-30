"""
Google Sheets integration (Service Account) for Seller Dashboard.

Not connected to live data until explicitly enabled and approved.
"""

from seller.google_sheets.auth import build_credentials, credentials_source_label
from seller.google_sheets.client import GoogleSheetsClient, get_sheets_client
from seller.google_sheets.config import GoogleSheetsSettings, get_settings, is_configured
from seller.google_sheets.status import get_integration_status

__all__ = [
    "GoogleSheetsClient",
    "GoogleSheetsSettings",
    "build_credentials",
    "credentials_source_label",
    "get_integration_status",
    "get_settings",
    "get_sheets_client",
    "is_configured",
]
