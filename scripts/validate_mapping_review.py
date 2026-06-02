#!/usr/bin/env python3
"""Validate FastMoss mapping review rules against known audit cases."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seller.fastmoss.mapping import MAPPING_MAPPED, load_fastmoss_mapping  # noqa: E402
from seller.fastmoss.review import (  # noqa: E402
    REVIEW_APPROVED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    list_review_rows,
    review_summary,
    save_review_store,
    sync_reviews_from_mappings,
    upsert_review_from_mapping,
)
from seller.intelligence.business.meta import build_business_seller_record  # noqa: E402

CASES = [
    {
        "shop_name": "LaLa_Shoes.PH",
        "tiktok_shop_name": "LALA",
        "expect_not_approved": True,
        "expect_statuses": {REVIEW_PENDING, REVIEW_REJECTED},
    },
    {
        "shop_name": "8% STORE Eight Percent",
        "tiktok_shop_name": "Eight Persent Store",
        "expect_not_approved": True,
        "expect_statuses": {REVIEW_PENDING, REVIEW_REJECTED},
    },
    {
        "shop_name": "Sklyer",
        "tiktok_shop_name": "Skyler Shop",
        "expect_not_approved": True,
        "expect_statuses": {REVIEW_PENDING},
    },
    {
        "shop_name": "Mumu PH",
        "tiktok_shop_name": "Mumu PH",
        "expect_not_approved": False,
        "expect_statuses": {REVIEW_APPROVED},
    },
]


def main() -> int:
    mapping_path = ROOT / "fastmoss_mapping.json"
    review_path = ROOT / "mapping_review_status.json"
    payload = load_fastmoss_mapping(mapping_path)
    mappings = payload.get("mappings") or []
    store = {"version": 1, "reviews": {}}
    audit_tiktok = {case["shop_name"]: case["tiktok_shop_name"] for case in CASES}
    for row in mappings:
        if not isinstance(row, dict):
            continue
        audit_row = dict(row)
        override = audit_tiktok.get(str(row.get("shop_name") or ""))
        if override:
            audit_row["tiktok_shop_name"] = override
        upsert_review_from_mapping(audit_row, store=store)
    save_review_store(store, ROOT / "mapping_review_status.json")

    rows_by_name = {str(r.get("shop_name")): r for r in list_review_rows(store)}
    summary = review_summary(store)
    results: list[dict] = []
    passed = True

    for case in CASES:
        row = rows_by_name.get(case["shop_name"])
        if not row:
            passed = False
            results.append({**case, "ok": False, "error": "Seller not found in review store"})
            continue
        status = row.get("review_status")
        ok = status in case["expect_statuses"]
        if case["expect_not_approved"] and status == REVIEW_APPROVED:
            ok = False
        if not case["expect_not_approved"] and status != REVIEW_APPROVED:
            ok = False

        mapping_row = next(m for m in mappings if m.get("shop_name") == case["shop_name"])
        bi = build_business_seller_record(
            shop_id=str(mapping_row.get("shop_id")),
            shop_name=str(mapping_row.get("shop_name")),
            tiktok_shop_name=case.get("tiktok_shop_name") or str(mapping_row.get("tiktok_shop_name")),
            mapping_row=mapping_row,
            collection_row={
                "status": "success",
                "mtd_gmv_php": 100,
                "m1_gmv_php": 90,
                "tiktok_mtd_adgmv_php": 10,
                "tiktok_m1_adgmv_php": 9,
            },
        )
        if case["expect_not_approved"] and bi.get("tiktok_data_status") != "na":
            ok = False
        if not case["expect_not_approved"] and bi.get("tiktok_data_status") != "available":
            ok = False

        passed = passed and ok
        results.append(
            {
                "shop_name": case["shop_name"],
                "review_status": status,
                "tiktok_data_status": bi.get("tiktok_data_status"),
                "tiktok_na_reason": bi.get("tiktok_na_reason"),
                "ok": ok,
            }
        )

    pending = [r for r in list_review_rows(store) if r.get("review_status") == REVIEW_PENDING][:10]
    rejected = [r for r in list_review_rows(store) if r.get("review_status") == REVIEW_REJECTED][:10]

    report = {
        "passed": passed,
        "summary": summary,
        "cases": results,
        "pending_preview": [
            {
                "shop_id": r.get("shop_id"),
                "shop_name": r.get("shop_name"),
                "tiktok_shop_name": r.get("tiktok_shop_name"),
                "fastmoss_shop_name": r.get("fastmoss_shop_name"),
                "review_status": r.get("review_status"),
            }
            for r in pending
        ],
        "rejected_preview": [
            {
                "shop_id": r.get("shop_id"),
                "shop_name": r.get("shop_name"),
                "tiktok_shop_name": r.get("tiktok_shop_name"),
                "fastmoss_shop_name": r.get("fastmoss_shop_name"),
                "review_status": r.get("review_status"),
            }
            for r in rejected
        ],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
