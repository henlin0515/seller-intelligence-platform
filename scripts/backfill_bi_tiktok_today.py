#!/usr/bin/env python3
"""Fetch current MTD/M-1 TikTok BI until every approved shop succeeds, then seed for Railway."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _rows_by_id(payload: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in payload.get("sellers") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("shop_id") or "").strip()
        if sid:
            out[sid] = row
    return out


def _counts(by_id: dict[str, dict]) -> tuple[int, int, list[str]]:
    ok = [sid for sid, r in by_id.items() if r.get("status") == "success"]
    bad = [sid for sid, r in by_id.items() if r.get("status") != "success"]
    return len(ok), len(bad), bad


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    from seller.fastmoss.client import anonymous_session
    from seller.fastmoss.recent_data import fetch_period_gmv_php
    from seller.fastmoss.review import approved_mapping_rows
    from seller.intelligence.business.bi_cache_refresh import (
        BiCacheRefreshError,
        build_bi_cache_payload,
        refresh_bi_cache,
    )
    from seller.intelligence.business.collector import collect_mapped_shop_tiktok
    from seller.intelligence.business.store import (
        load_business_intelligence_data,
        save_business_intelligence_data,
    )
    from seller.intelligence.business_time import business_today
    from seller.intelligence.periods import resolve_periods

    today = business_today()
    periods = resolve_periods(today)
    approved = approved_mapping_rows()
    print(
        f"BI backfill today={today} approved={len(approved)} "
        f"MTD={periods.mtd.start}..{periods.mtd.end} M1={periods.m1.start}..{periods.m1.end}",
        flush=True,
    )
    if not approved:
        print("No approved mappings", flush=True)
        return 1

    # Soft probe: JSON recentData only (no HTML homepage / detail prefetch).
    probe = approved[0]
    probe_fm = str(probe.get("fastmoss_shop_id") or "")
    try:
        sess = anonymous_session()
        mtd_gmv, _, sess = fetch_period_gmv_php(
            probe_fm, periods.mtd.start, periods.mtd.end, session=sess, prefetch_detail=False
        )
        print(f"probe ok shop={probe.get('shop_id')} mtd_php={mtd_gmv}", flush=True)
    except Exception as exc:
        print(f"probe FAILED: {exc}", flush=True)
        return 1

    delay = float(os.getenv("BI_BACKFILL_DELAY_SEC", "1.0"))
    max_rounds = int(os.getenv("BI_BACKFILL_MAX_ROUNDS", "8"))

    print(f"\n=== full refresh delay={delay}s ===", flush=True)
    try:
        result = refresh_bi_cache(
            delay_sec=delay,
            reference_today=today,
            trigger="local_backfill",
            invalidate_first=False,
            skip_healthcheck=True,
        )
        print(
            json.dumps(
                {
                    "collection_success": result.get("collection_success"),
                    "updated_count": result.get("updated_count"),
                    "elapsed_sec": result.get("elapsed_sec"),
                },
                indent=2,
            ),
            flush=True,
        )
    except BiCacheRefreshError as exc:
        print(f"full refresh error: {exc}", flush=True)

    payload = load_business_intelligence_data() or {}
    by_id = _rows_by_id(payload)
    for row in approved:
        sid = str(row.get("shop_id") or "").strip()
        if sid and sid not in by_id:
            by_id[sid] = {
                "shop_id": sid,
                "shop_name": row.get("shop_name"),
                "status": "failed",
                "error": "missing_from_collection",
            }

    ok, bad, bad_ids = _counts(by_id)
    print(f"after full refresh success={ok} failed={bad}", flush=True)

    approved_by_id = {str(r.get("shop_id")): r for r in approved if r.get("shop_id")}

    for round_idx in range(1, max_rounds + 1):
        ok, bad, bad_ids = _counts(by_id)
        if bad == 0 and ok == len(approved):
            break
        print(f"\n=== retry round {round_idx}/{max_rounds} failed={bad} ===", flush=True)
        recovered = 0
        for index, sid in enumerate(list(bad_ids)):
            mapping = approved_by_id.get(sid)
            if not mapping:
                continue
            if index > 0 and delay > 0:
                time.sleep(delay)
            try:
                collected = collect_mapped_shop_tiktok(
                    mapping, periods, delay_sec=0, session=anonymous_session()
                )
            except Exception as exc:
                collected = {
                    "shop_id": sid,
                    "shop_name": mapping.get("shop_name"),
                    "status": "failed",
                    "error": str(exc),
                }
            collected.setdefault("mtd_start", periods.mtd.start.isoformat())
            collected.setdefault("mtd_end", periods.mtd.end.isoformat())
            collected.setdefault("m1_start", periods.m1.start.isoformat())
            collected.setdefault("m1_end", periods.m1.end.isoformat())
            by_id[sid] = collected
            if collected.get("status") == "success":
                recovered += 1
                print(
                    f"  recovered {sid} mtd={collected.get('mtd_gmv_php')} "
                    f"m1={collected.get('m1_gmv_php')}",
                    flush=True,
                )
            else:
                print(f"  still fail {sid}: {collected.get('error')}", flush=True)

        sellers = [
            by_id[str(r.get("shop_id"))]
            for r in approved
            if str(r.get("shop_id") or "") in by_id
        ]
        payload = build_bi_cache_payload(
            reference_today=today, periods=periods, sellers=sellers
        )
        save_business_intelligence_data(payload)
        ok, bad, bad_ids = _counts(by_id)
        print(f"round done recovered={recovered} success={ok} failed={bad}", flush=True)
        if bad == 0:
            break
        time.sleep(2)

    ok, bad, bad_ids = _counts(by_id)
    sellers = [
        by_id[str(r.get("shop_id"))]
        for r in approved
        if str(r.get("shop_id") or "") in by_id
    ]
    payload = build_bi_cache_payload(reference_today=today, periods=periods, sellers=sellers)
    save_business_intelligence_data(payload)

    summary = {
        "reference_today": payload.get("reference_today"),
        "periods": payload.get("periods"),
        "success": ok,
        "failed": bad,
        "total_approved": len(approved),
        "failed_shop_ids": bad_ids,
        "generated_at": payload.get("generated_at"),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)

    if bad != 0 or ok != len(approved):
        print("NOT 100% — abort upload", flush=True)
        return 1

    seed = ROOT / "business_intelligence_data.seed.json"
    seed.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote seed {seed}", flush=True)

    try:
        from seller.intelligence.business.sla_update_state import sync_sla_update_state_from_bi

        sync_sla_update_state_from_bi(
            generated_at=str(payload.get("generated_at")),
            reference_today=str(today),
            tiktok_success=ok,
        )
        print("SLA state synced", flush=True)
    except Exception as exc:
        print(f"SLA sync skipped: {exc}", flush=True)

    print("100% SUCCESS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
