"""Strict freshness: failed shops must not reuse prior ADGMV as current KPI."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from seller.intelligence.business.bi_cache_refresh import refresh_bi_cache
from seller.intelligence.business.bi_validation import validate_bi_sellers
from seller.intelligence.business.collector import (
    STATUS_FETCH_FAILED,
    classify_collect_error,
    row_is_fresh_success,
    success_snapshot,
)
from seller.intelligence.periods import resolve_periods


def test_classify_auth_and_rate_limit():
    assert classify_collect_error(RuntimeError("HTTP 401")) == "AUTH"
    assert classify_collect_error(RuntimeError("429 Too Many")) == "RATE_LIMIT"
    assert classify_collect_error(RuntimeError("missing total_info.sale_amount")) == (
        "INVALID_RESPONSE"
    )
    assert classify_collect_error(RuntimeError("timeout")) == "FETCH_FAILED"


def test_row_is_fresh_success_requires_today():
    today = date(2026, 7, 24)
    assert row_is_fresh_success(
        {"status": "success", "data_date": "2026-07-24"}, today=today
    )
    assert not row_is_fresh_success(
        {"status": "success", "data_date": "2026-07-23"}, today=today
    )
    assert not row_is_fresh_success(
        {"status": "FETCH_FAILED", "data_date": "2026-07-24"}, today=today
    )


def test_refresh_failed_shop_current_adgmv_null_keeps_snapshot(tmp_path: Path):
    today = date(2026, 7, 24)
    periods = resolve_periods(today)
    cache = tmp_path / "business_intelligence_data.json"
    previous = {
        "reference_today": today.isoformat(),
        "periods": periods.as_dict(),
        "cache_status": "ready",
        "summary": {"success": 2, "processed": 2, "failed": 0},
        "sellers": [
            {
                "shop_id": "1",
                "status": "success",
                "data_date": today.isoformat(),
                "fetched_at": "2026-07-24T01:00:00Z",
                "tiktok_mtd_adgmv_php": 100.0,
                "tiktok_m1_adgmv_php": 90.0,
                "mtd_gmv_php": 2300.0,
                "m1_gmv_php": 2070.0,
                "mtd_start": periods.mtd.start.isoformat(),
                "mtd_end": periods.mtd.end.isoformat(),
                "m1_start": periods.m1.start.isoformat(),
                "m1_end": periods.m1.end.isoformat(),
            },
            {
                "shop_id": "2",
                "status": "success",
                "data_date": today.isoformat(),
                "fetched_at": "2026-07-24T01:00:00Z",
                "tiktok_mtd_adgmv_php": 200.0,
                "tiktok_m1_adgmv_php": 180.0,
                "mtd_gmv_php": 4600.0,
                "m1_gmv_php": 4140.0,
                "mtd_start": periods.mtd.start.isoformat(),
                "mtd_end": periods.mtd.end.isoformat(),
                "m1_start": periods.m1.start.isoformat(),
                "m1_end": periods.m1.end.isoformat(),
            },
        ],
    }
    cache.write_text(json.dumps(previous), encoding="utf-8")

    def collect(row, periods_arg, delay_sec=0, session=None, data_date=None, previous_row=None):
        if row["shop_id"] == "1":
            return {
                "shop_id": "1",
                "shop_name": "A",
                "fastmoss_shop_id": "fm1",
                "status": STATUS_FETCH_FAILED,
                "error": "502",
                "data_date": today.isoformat(),
                "tiktok_mtd_adgmv_php": None,
                "tiktok_m1_adgmv_php": None,
                "last_successful_snapshot": success_snapshot(previous_row),
            }
        return {
            "shop_id": "2",
            "shop_name": "B",
            "fastmoss_shop_id": "fm2",
            "status": "success",
            "data_date": today.isoformat(),
            "tiktok_mtd_adgmv_php": 210.0,
            "tiktok_m1_adgmv_php": 180.0,
            "mtd_gmv_php": 4830.0,
            "m1_gmv_php": 4140.0,
            "mtd_start": periods_arg.mtd.start.isoformat(),
            "mtd_end": periods_arg.mtd.end.isoformat(),
            "m1_start": periods_arg.m1.start.isoformat(),
            "m1_end": periods_arg.m1.end.isoformat(),
        }

    with (
        patch(
            "seller.intelligence.business.bi_cache_refresh.approved_mapping_rows",
            return_value=[
                {
                    "shop_id": "1",
                    "shop_name": "A",
                    "tiktok_shop_name": "A",
                    "fastmoss_shop_id": "fm1",
                    "mapping_status": "MAPPED",
                },
                {
                    "shop_id": "2",
                    "shop_name": "B",
                    "tiktok_shop_name": "B",
                    "fastmoss_shop_id": "fm2",
                    "mapping_status": "MAPPED",
                },
            ],
        ),
        patch(
            "seller.intelligence.business.bi_cache_refresh.bi_data_path",
            return_value=cache,
        ),
        patch(
            "seller.intelligence.business.store.DEFAULT_BI_DATA_PATH",
            cache,
        ),
        patch(
            "seller.intelligence.business.bi_cache_refresh.load_business_intelligence_data",
            side_effect=lambda path=None: (
                json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else None
            ),
        ),
        patch(
            "seller.intelligence.business.store.load_business_intelligence_data",
            side_effect=lambda path=None: (
                json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else None
            ),
        ),
        patch(
            "seller.intelligence.business.bi_cache_refresh.save_business_intelligence_data",
            side_effect=lambda payload, path=None: (
                cache.write_text(json.dumps(payload), encoding="utf-8") or cache
            ),
        ),
        patch(
            "seller.intelligence.business.store.save_business_intelligence_data",
            side_effect=lambda payload, path=None: (
                cache.write_text(json.dumps(payload), encoding="utf-8") or cache
            ),
        ),
    ):
        result = refresh_bi_cache(
            delay_sec=0,
            reference_today=today,
            trigger="test",
            collect_fn=collect,
            skip_healthcheck=True,
            invalidate_first=False,
        )

    assert result["success"] is True
    assert result["collection_success"] == 1
    assert result["collection_failed"] == 1
    saved = json.loads(cache.read_text(encoding="utf-8"))
    by_id = {r["shop_id"]: r for r in saved["sellers"]}
    assert by_id["1"]["status"] == STATUS_FETCH_FAILED
    assert by_id["1"]["tiktok_mtd_adgmv_php"] is None
    assert by_id["1"]["tiktok_m1_adgmv_php"] is None
    assert by_id["1"]["last_successful_snapshot"]["tiktok_mtd_adgmv_php"] == 100.0
    assert by_id["1"].get("preserved_from_previous") is None
    assert by_id["2"]["tiktok_mtd_adgmv_php"] == 210.0
    assert by_id["2"]["status"] == "success"


def test_validation_lists_missing_failed_stale_invalid():
    today = date(2026, 7, 24)
    periods = resolve_periods(today)
    sellers = [
        {
            "shop_id": "ok",
            "shop_name": "OK",
            "fastmoss_shop_id": "fm-ok",
            "fastmoss_shop_url": "https://www.fastmoss.com/shop-marketing/detail/fm-ok",
            "status": "success",
            "data_date": today.isoformat(),
            "mtd_gmv_php": 100.0,
            "m1_gmv_php": 90.0,
            "tiktok_mtd_adgmv_php": 10.0,
            "tiktok_m1_adgmv_php": 9.0,
            "mtd_start": periods.mtd.start.isoformat(),
            "mtd_end": periods.mtd.end.isoformat(),
            "m1_start": periods.m1.start.isoformat(),
            "m1_end": periods.m1.end.isoformat(),
        },
        {
            "shop_id": "miss",
            "shop_name": "Miss",
            "fastmoss_shop_id": "",
            "status": "MISSING_FASTMOSS_ID",
            "data_date": today.isoformat(),
        },
        {
            "shop_id": "fail",
            "shop_name": "Fail",
            "fastmoss_shop_id": "fm-fail",
            "fastmoss_shop_url": "https://www.fastmoss.com/shop-marketing/detail/fm-fail",
            "status": "FETCH_FAILED",
            "error": "502",
            "data_date": today.isoformat(),
            "tiktok_mtd_adgmv_php": None,
        },
        {
            "shop_id": "stale",
            "shop_name": "Stale",
            "fastmoss_shop_id": "fm-stale",
            "fastmoss_shop_url": "https://www.fastmoss.com/shop-marketing/detail/fm-stale",
            "status": "success",
            "data_date": "2026-07-23",
            "mtd_gmv_php": 1.0,
            "m1_gmv_php": 1.0,
            "tiktok_mtd_adgmv_php": 1.0,
            "tiktok_m1_adgmv_php": 1.0,
            "mtd_start": periods.mtd.start.isoformat(),
            "mtd_end": periods.mtd.end.isoformat(),
            "m1_start": periods.m1.start.isoformat(),
            "m1_end": periods.m1.end.isoformat(),
        },
        {
            "shop_id": "bad",
            "shop_name": "Bad",
            "fastmoss_shop_id": "fm-bad",
            "fastmoss_shop_url": "https://www.fastmoss.com/shop-marketing/detail/fm-bad",
            "status": "success",
            "data_date": today.isoformat(),
            "mtd_gmv_php": 1.0,
            "m1_gmv_php": 1.0,
            "tiktok_mtd_adgmv_php": None,
            "tiktok_m1_adgmv_php": 1.0,
            "mtd_start": periods.mtd.start.isoformat(),
            "mtd_end": periods.mtd.end.isoformat(),
            "m1_start": periods.m1.start.isoformat(),
            "m1_end": periods.m1.end.isoformat(),
        },
    ]
    report = validate_bi_sellers(sellers, today=today, periods=periods)
    assert report["total_shops"] == 5
    assert report["fetch_success"] == 1
    assert report["missing_fastmoss_id"] == 1
    assert report["fetch_failed"] == 1
    assert report["stale"] == 1
    assert report["invalid_response"] == 1
    assert report["all_success"] is False
    assert report["success_label"] == "1/5 SUCCESS"
    assert report["failed_label"] == "4 FAILED"


def test_all_success_only_when_every_shop_fresh():
    today = date(2026, 7, 24)
    periods = resolve_periods(today)
    sellers = [
        {
            "shop_id": str(i),
            "shop_name": f"S{i}",
            "fastmoss_shop_id": f"fm{i}",
            "fastmoss_shop_url": f"https://www.fastmoss.com/shop-marketing/detail/fm{i}",
            "status": "success",
            "data_date": today.isoformat(),
            "mtd_gmv_php": 10.0,
            "m1_gmv_php": 9.0,
            "tiktok_mtd_adgmv_php": 1.0,
            "tiktok_m1_adgmv_php": 0.9,
            "mtd_start": periods.mtd.start.isoformat(),
            "mtd_end": periods.mtd.end.isoformat(),
            "m1_start": periods.m1.start.isoformat(),
            "m1_end": periods.m1.end.isoformat(),
        }
        for i in range(3)
    ]
    report = validate_bi_sellers(sellers, today=today, periods=periods)
    assert report["all_success"] is True
    assert report["success_label"] == "3/3 SUCCESS"
