"""Quick check for Google Sheets env validation (no API calls)."""
from __future__ import annotations

import os

from dotenv import load_dotenv

from seller.google_sheets.config import (
    clear_settings_cache,
    get_credentials_source,
    is_configured,
    is_credentials_usable,
    validate_for_connection,
)


def run_case(label: str) -> None:
    clear_settings_cache()
    print(f"\n=== {label} ===")
    print("source:", get_credentials_source())
    print("usable:", is_credentials_usable(), "configured:", is_configured())
    print("issues:", validate_for_connection())


def main() -> None:
    load_dotenv()
    run_case("Local .env")

    os.environ["GOOGLE_SHEETS_ENABLED"] = "true"
    os.environ["GOOGLE_SHEET_MIRROR_ID"] = "test-id"
    os.environ.pop("GOOGLE_SHEETS_CREDENTIALS_PATH", None)
    os.environ["GOOGLE_SHEETS_CREDENTIALS_JSON"] = (
        '{"type":"service_account","project_id":"demo","client_email":"a@b.iam.gserviceaccount.com"}'
    )
    run_case("Railway-like JSON only")

    os.environ["GOOGLE_SHEETS_CREDENTIALS_PATH"] = "credentials/missing.json"
    os.environ.pop("GOOGLE_SHEETS_CREDENTIALS_JSON", None)
    run_case("Path set but file missing (should fail)")


if __name__ == "__main__":
    main()
