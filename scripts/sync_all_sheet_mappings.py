#!/usr/bin/env python3
"""Sync all sheet shops to FastMoss mapping + TikTok BI + Historical SOB (full pipeline)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> int:
    from seller.fastmoss.mapping import load_fastmoss_mapping, refresh_all_sheet_fastmoss_mapping
    from seller.intelligence.business.sla_refresh import run_sla_refresh_job
    from seller.intelligence.seller_master import get_seller_master

    print("=== Step 1: Reload seller master from Google Sheet ===")
    master = get_seller_master(force_refresh=True)
    print(f"Loaded {len(master.sellers)} sellers from tab {master.tab!r}")

    print("\n=== Step 2: FastMoss mapping for shops that need search ===")
    map_result = refresh_all_sheet_fastmoss_mapping()
    print(json.dumps(map_result, indent=2, ensure_ascii=False))

    payload = load_fastmoss_mapping()
    summary = payload.get("summary") or {}
    print(
        f"Mapping summary: mapped={summary.get('mapped')} "
        f"need_review={summary.get('need_review')} not_found={summary.get('not_found')} "
        f"total={summary.get('total')}"
    )

    print("\n=== Step 3: Full SLA pipeline (TikTok BI + Historical SOB + persist state) ===")
    print("(This may take several minutes for ~95 shops…)")
    sla_result = run_sla_refresh_job()
    print(json.dumps(sla_result, indent=2, ensure_ascii=False)[:4000])

    if not sla_result.get("success"):
        print("FAIL: SLA sync did not complete successfully")
        return 1

    print("\nDONE — mapping and BI data saved locally. Deploy or restart Railway to apply on production.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
