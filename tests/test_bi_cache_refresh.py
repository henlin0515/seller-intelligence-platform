"""Tests for atomic BI cache refresh and daily scheduler."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from seller.intelligence.business.bi_cache_refresh import (
    BiCacheRefreshError,
    bi_cache_needs_daily_refresh,
    refresh_bi_cache,
)
from seller.intelligence.business.bi_daily_scheduler import next_daily_run_utc
from seller.intelligence.business.collector import daily_adgmv_php
from seller.intelligence.periods import resolve_periods


def _mapping_row(shop_id: str = "1") -> dict:
    return {
        "shop_id": shop_id,
        "shop_name": f"Shop {shop_id}",
        "tiktok_shop_name": f"TT {shop_id}",
        "fastmoss_shop_id": f"fm-{shop_id}",
        "fastmoss_shop_name": f"FM {shop_id}",
        "mapping_status": "MAPPED",
    }


def test_refresh_overwrites_cache_on_success(tmp_path: Path):
    cache = tmp_path / "business_intelligence_data.json"
    cache.write_text(
        json.dumps(
            {
                "reference_today": "2026-06-16",
                "periods": resolve_periods(date(2026, 6, 16)).as_dict(),
                "sellers": [{"shop_id": "old", "status": "success"}],
                "summary": {"success": 1},
            }
        ),
        encoding="utf-8",
    )
    today = date(2026, 7, 23)
    periods = resolve_periods(today)

    def fake_collect(row, periods_arg, delay_sec=0):
        mtd_gmv = 220.0
        m1_gmv = 110.0
        return {
            "shop_id": row["shop_id"],
            "shop_name": row["shop_name"],
            "status": "success",
            "mtd_gmv_php": mtd_gmv,
            "m1_gmv_php": m1_gmv,
            "tiktok_mtd_adgmv_php": daily_adgmv_php(mtd_gmv, periods_arg.mtd.day_count),
            "tiktok_m1_adgmv_php": daily_adgmv_php(m1_gmv, periods_arg.m1.day_count),
            "mtd_start": periods_arg.mtd.start.isoformat(),
            "mtd_end": periods_arg.mtd.end.isoformat(),
            "m1_start": periods_arg.m1.start.isoformat(),
            "m1_end": periods_arg.m1.end.isoformat(),
        }

    with (
        patch(
            "seller.intelligence.business.bi_cache_refresh.approved_mapping_rows",
            return_value=[_mapping_row("1"), _mapping_row("2")],
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
            collect_fn=fake_collect,
            skip_healthcheck=True,
        )

    assert result["success"] is True
    assert result["cache_overwritten"] is True
    assert result["updated_count"] == 2
    assert result["bi_date"] == "2026-07-23"
    assert result["periods"]["mtd"] == {
        "start": periods.mtd.start.isoformat(),
        "end": periods.mtd.end.isoformat(),
    }
    assert result["periods"]["m1"] == {
        "start": periods.m1.start.isoformat(),
        "end": periods.m1.end.isoformat(),
    }
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert saved["reference_today"] == "2026-07-23"
    assert len(saved["sellers"]) == 2
    row = saved["sellers"][0]
    assert row["tiktok_mtd_adgmv_php"] == pytest.approx(
        daily_adgmv_php(220.0, periods.mtd.day_count)
    )


def test_refresh_invalidates_wrong_period_cache_on_failure(tmp_path: Path):
    cache = tmp_path / "business_intelligence_data.json"
    previous = {
        "reference_today": "2026-06-16",
        "periods": resolve_periods(date(2026, 6, 16)).as_dict(),
        "sellers": [{"shop_id": "old", "status": "success", "mtd_gmv_php": 999}],
        "summary": {"success": 1},
        "cache_status": "ready",
    }
    cache.write_text(json.dumps(previous), encoding="utf-8")

    def fail_collect(row, periods_arg, delay_sec=0):
        return {
            "shop_id": row["shop_id"],
            "status": "failed",
            "error": "boom",
            "tiktok_mtd_adgmv_php": None,
        }

    with (
        patch(
            "seller.intelligence.business.bi_cache_refresh.approved_mapping_rows",
            return_value=[_mapping_row("1")],
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
        with pytest.raises(BiCacheRefreshError):
            refresh_bi_cache(
                delay_sec=0,
                reference_today=date(2026, 7, 23),
                trigger="test_fail",
                collect_fn=fail_collect,
                skip_healthcheck=True,
            )

    saved = json.loads(cache.read_text(encoding="utf-8"))
    # Wrong-period refresh failure must not keep June ADGMV as current success.
    assert saved.get("cache_status") == "ready"
    assert saved["periods"]["mtd"]["start"] == "2026-07-01"
    assert saved["periods"]["mtd"]["end"] == "2026-07-22"
    assert saved["summary"]["success"] == 0
    assert all(row.get("status") != "success" for row in saved.get("sellers") or [])
    assert all(row.get("tiktok_mtd_adgmv_php") is None for row in saved.get("sellers") or [])


def test_bi_cache_needs_daily_refresh_when_day_differs():
    saved = {
        "reference_today": "2026-06-16",
        "periods": resolve_periods(date(2026, 6, 16)).as_dict(),
    }
    with patch(
        "seller.intelligence.business.bi_cache_refresh.load_business_intelligence_data",
        return_value=saved,
    ):
        needs, reason = bi_cache_needs_daily_refresh(reference_today=date(2026, 7, 23))
    assert needs is True
    assert "2026-06-16" in reason


def test_next_daily_run_rolls_forward():
    now = datetime(2026, 7, 23, 16, 10, tzinfo=timezone.utc)
    with (
        patch("seller.intelligence.business.bi_daily_scheduler._refresh_hour_utc", return_value=16),
        patch("seller.intelligence.business.bi_daily_scheduler._refresh_minute_utc", return_value=5),
    ):
        nxt = next_daily_run_utc(now)
    assert nxt.date() == date(2026, 7, 24)
    assert nxt.hour == 16 and nxt.minute == 5
