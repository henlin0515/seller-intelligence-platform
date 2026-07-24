"""FastMoss TikTok BI must align with UI MTD / M-1 period tags."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from seller.intelligence.business.meta import (
    EMPTY_TIKTOK_NAME_NA,
    TIKTOK_PERIODS_STALE_NA,
    build_business_seller_record,
    get_business_intelligence_meta,
)
from seller.intelligence.business.collector import daily_adgmv_php
from seller.intelligence.periods import resolve_periods


def test_daily_adgmv_uses_inclusive_day_count():
    assert daily_adgmv_php(220.0, 22) == 10.0


def test_stale_collection_hidden_for_mapped_shop():
    periods = resolve_periods(date(2026, 7, 23))
    mapping = {
        "mapping_status": "MAPPED",
        "tiktok_shop_name": "Demo TT",
        "fastmoss_shop_name": "Demo TT",
        "fastmoss_shop_id": "123",
        "confidence": 1.0,
    }
    collection = {
        "status": "success",
        "mtd_gmv_php": 2200.0,
        "m1_gmv_php": 1100.0,
        "tiktok_mtd_adgmv_php": 100.0,
        "tiktok_m1_adgmv_php": 50.0,
        "mtd_start": "2026-06-01",
        "mtd_end": "2026-06-15",
        "m1_start": "2026-05-01",
        "m1_end": "2026-05-15",
    }
    with patch(
        "seller.intelligence.business.meta.get_review_by_shop_id",
        return_value={"review_status": "APPROVED"},
    ):
        record = build_business_seller_record(
            shop_id="1",
            shop_name="Demo",
            tiktok_shop_name="Demo TT",
            mapping_row=mapping,
            collection_row=collection,
            periods_stale=True,
            current_periods=periods,
        )
    assert record["tiktok_data_status"] == "na"
    assert record["tiktok_na_reason"] == TIKTOK_PERIODS_STALE_NA
    assert record["tiktok_mtd_adgmv_usd"] is None
    assert record["tiktok_mom_percent"] is None


def test_aligned_collection_applies_adgmv_and_mom():
    periods = resolve_periods(date(2026, 7, 23))
    mapping = {
        "mapping_status": "MAPPED",
        "tiktok_shop_name": "Demo TT",
        "fastmoss_shop_name": "Demo TT",
        "fastmoss_shop_id": "123",
        "confidence": 1.0,
    }
    collection = {
        "status": "success",
        "data_date": "2026-07-23",
        "mtd_gmv_php": 2200.0,
        "m1_gmv_php": 1100.0,
        "tiktok_mtd_adgmv_php": 100.0,
        "tiktok_m1_adgmv_php": 50.0,
        "mtd_start": periods.mtd.start.isoformat(),
        "mtd_end": periods.mtd.end.isoformat(),
        "m1_start": periods.m1.start.isoformat(),
        "m1_end": periods.m1.end.isoformat(),
    }
    with (
        patch(
            "seller.intelligence.business.meta.get_review_by_shop_id",
            return_value={"review_status": "APPROVED"},
        ),
        patch(
            "seller.intelligence.business.meta.business_today",
            return_value=date(2026, 7, 23),
        ),
    ):
        record = build_business_seller_record(
            shop_id="1",
            shop_name="Demo",
            tiktok_shop_name="Demo TT",
            mapping_row=mapping,
            collection_row=collection,
            periods_stale=False,
            current_periods=periods,
        )
    assert record["tiktok_data_status"] == "available"
    assert record["tiktok_mom_percent"] == 100.0


def test_stale_data_date_hides_adgmv_even_if_status_success():
    periods = resolve_periods(date(2026, 7, 24))
    mapping = {
        "mapping_status": "MAPPED",
        "tiktok_shop_name": "Demo TT",
        "fastmoss_shop_name": "Demo TT",
        "fastmoss_shop_id": "123",
        "confidence": 1.0,
    }
    collection = {
        "status": "success",
        "data_date": "2026-07-23",
        "tiktok_mtd_adgmv_php": 100.0,
        "tiktok_m1_adgmv_php": 50.0,
        "mtd_gmv_php": 2200.0,
        "m1_gmv_php": 1100.0,
        "mtd_start": periods.mtd.start.isoformat(),
        "mtd_end": periods.mtd.end.isoformat(),
        "m1_start": periods.m1.start.isoformat(),
        "m1_end": periods.m1.end.isoformat(),
        "last_successful_snapshot": {"tiktok_mtd_adgmv_php": 100.0},
    }
    with (
        patch(
            "seller.intelligence.business.meta.get_review_by_shop_id",
            return_value={"review_status": "APPROVED"},
        ),
        patch(
            "seller.intelligence.business.meta.business_today",
            return_value=date(2026, 7, 24),
        ),
    ):
        record = build_business_seller_record(
            shop_id="1",
            shop_name="Demo",
            tiktok_shop_name="Demo TT",
            mapping_row=mapping,
            collection_row=collection,
            periods_stale=False,
            current_periods=periods,
        )
    assert record["tiktok_data_status"] == "stale"
    assert record["tiktok_mtd_adgmv_usd"] is None
    assert record["tiktok_mom_percent"] is None


def test_empty_tiktok_name_na_reason():
    mapping = {
        "mapping_status": "NOT_FOUND",
        "tiktok_shop_name": "",
        "failure_reason": "empty_tiktok_shop_name",
    }
    with patch(
        "seller.intelligence.business.meta.get_review_by_shop_id",
        return_value=None,
    ):
        record = build_business_seller_record(
            shop_id="35369989",
            shop_name="ICM.STORE",
            tiktok_shop_name="",
            mapping_row=mapping,
            collection_row=None,
            periods_stale=True,
            current_periods=resolve_periods(date(2026, 7, 23)),
        )
    assert record["tiktok_data_status"] == "na"
    assert record["tiktok_na_reason"] == EMPTY_TIKTOK_NAME_NA


def test_meta_marks_stale_when_cached_periods_differ():
    saved = {
        "generated_at": "2026-06-16T07:47:17Z",
        "reference_today": "2026-06-16",
        "periods": resolve_periods(date(2026, 6, 16)).as_dict(),
        "summary": {"success": 1},
        "source": "fastmoss_recentData",
        "sellers": [],
    }
    with patch(
        "seller.intelligence.business.meta.load_business_intelligence_data",
        return_value=saved,
    ):
        meta = get_business_intelligence_meta(reference_today=date(2026, 7, 23))
    assert meta["periods_stale"] is True
    assert meta["current_periods"]["mtd"]["end"] == "2026-07-22"
