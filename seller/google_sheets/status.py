"""
Integration status for Seller Dashboard (no live sheet load).
"""

from __future__ import annotations

from typing import Any

from seller.google_sheets.auth import credentials_source_label, service_account_email
from seller.google_sheets.config import get_settings, is_configured, validate_for_connection


def get_integration_status() -> dict[str, Any]:
    """
    Safe summary for logs or a future /api/seller/status endpoint.
    Does not call Google APIs unless a separate ping is requested later.
    """
    s = get_settings()
    issues = validate_for_connection()
    return {
        "enabled": s.enabled,
        "configured": is_configured(),
        "ready_to_connect": s.enabled and not issues,
        "spreadsheet_id_set": bool(s.has_spreadsheet_id),
        "credentials_source": credentials_source_label(s),
        "service_account_email": service_account_email(s),
        "primary_tab_hint": s.primary_tab_hint,
        "connect_on_startup": s.connect_on_startup,
        "data_source_active": (
            "google_sheets"
            if s.enabled and is_configured()
            else "mock"
        ),
        "configuration_issues": issues,
        "scopes": list(s.scopes),
    }
