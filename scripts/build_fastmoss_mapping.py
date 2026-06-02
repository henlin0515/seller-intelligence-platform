#!/usr/bin/env python3
"""Task A: build fastmoss_mapping.json from seller master (search only)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from seller.fastmoss.mapping import build_fastmoss_mapping  # noqa: E402
from seller.google_sheets.config import is_configured, validate_for_connection  # noqa: E402
from seller.intelligence.seller_master import clear_seller_master_cache  # noqa: E402


def main() -> int:
    print("=== FastMoss mapping (Task A — search only) ===")
    if not is_configured():
        print("Google Sheets not configured:")
        for issue in validate_for_connection():
            print(f"  - {issue}")
        return 1

    clear_seller_master_cache()
    payload = build_fastmoss_mapping()
    out_path = ROOT / "fastmoss_mapping.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = payload["summary"]
    print(f"\nWrote {out_path}")
    print(f"Total shops: {summary['total']}")
    print(f"MAPPED: {summary['mapped']}")
    print(f"NEED_REVIEW: {summary['need_review']}")
    print(f"NOT_FOUND: {summary['not_found']}")

    print("\nFirst 10 mapping results:")
    for row in payload["mappings"][:10]:
        print(json.dumps(row, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
