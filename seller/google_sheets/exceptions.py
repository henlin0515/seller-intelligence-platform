"""Google Sheets integration errors."""


class GoogleSheetsError(Exception):
    """Base error for Seller Dashboard Google Sheets layer."""


class GoogleSheetsNotConfiguredError(GoogleSheetsError):
    """Required env vars or credentials are missing."""


class GoogleSheetsAuthError(GoogleSheetsError):
    """Service Account credentials could not be loaded or authorized."""


class GoogleSheetsNotEnabledError(GoogleSheetsError):
    """Integration is disabled (GOOGLE_SHEETS_ENABLED=false)."""
