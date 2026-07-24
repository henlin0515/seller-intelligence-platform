"""Preserve previous BI success when a shop collect fails mid-refresh."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from seller.intelligence.business.bi_cache_refresh import refresh_bi_cache
from seller.intelligence.periods import resolve_periods


def test_refresh_preserves_previous_success_on_partial_failure(tmp_path: Path):
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
                "tiktok_mtd_adgmv_php": 100.0,
                "tiktok_m1_adgmv_php": 90.0,
                "mtd_start": periods.mtd.start.isoformat(),
                "mtd_end": periods.mtd.end.isoformat(),
                "m1_start": periods.m1.start.isoformat(),
                "m1_end": periods.m1.end.isoformat(),
            },
            {
                "shop_id": "2",
                "status": "success",
                "tiktok_mtd_adgmv_php": 200.0,
                "tiktok_m1_adgmv_php": 180.0,
                "mtd_start": periods.mtd.start.isoformat(),
                "mtd_end": periods.mtd.end.isoformat(),
                "m1_start": periods.m1.start.isoformat(),
                "m1_end": periods.m1.end.isoformat(),
            },
        ],
    }
    cache.write_text(json.dumps(previous), encoding="utf-8")

    def collect(row, periods_arg, delay_sec=0, session=None):
        if row["shop_id"] == "1":
            return {
                "shop_id": "1",
                "status": "failed",
                "error": "502",
                "tiktok_mtd_adgmv_php": None,
            }
        return {
            "shop_id": "2",
            "status": "success",
            "tiktok_mtd_adgmv_php": 210.0,
            "tiktok_m1_adgmv_php": 180.0,
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
    saved = json.loads(cache.read_text(encoding="utf-8"))
    by_id = {r["shop_id"]: r for r in saved["sellers"]}
    assert by_id["1"]["tiktok_mtd_adgmv_php"] == 100.0
    assert by_id["1"].get("preserved_from_previous") is True
    assert by_id["2"]["tiktok_mtd_adgmv_php"] == 210.0
