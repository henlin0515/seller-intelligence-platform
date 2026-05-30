"""
Verify mirror sheet access and print merge summary.
Run from project root with .env configured:

  python scripts/load_mirror_sheet.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from seller.sheets_cache import get_load_summary, refresh  # noqa: E402


def main() -> int:
    try:
        refresh(force=True)
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1

    summary = get_load_summary() or {}
    layout = summary.get("layout") or {}

    print("--- Mirror sheet load summary ---")
    print(f"Header row used: {layout.get('header_row', summary.get('header_row', 'N/A'))}")
    print(f"Data start row used: {layout.get('data_start_row', 'N/A')}")
    print(f"Shop ID column: {layout.get('shop_id_column', 'J')}")
    print(f"Shop Name column: {layout.get('shop_name_column', 'K')}")
    print(f"Total seller rows loaded: {summary.get('total_seller_rows_loaded', summary.get('seller_count', 0))}")
    print(f"Total columns loaded: {summary.get('total_columns_loaded', 'N/A')}")
    print(f"Primary tab: {summary.get('primary_tab')}")
    print(f"Shop ID header: {layout.get('shop_id_header', summary.get('shop_id_field'))}")
    print("--- Full JSON ---")
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
