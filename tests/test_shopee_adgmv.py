"""Shopee Tracker totals → daily ADGMV tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from seller.intelligence.business.calculations import (
    mom_percent,
    shopee_period_totals_to_adgmv,
)
from seller.intelligence.business.meta import build_business_seller_record
from seller.intelligence.business.shopee_adgmv import (
    ShopeeAdgmvRecord,
    parse_shopee_adgmv_rows,
)
from seller.intelligence.periods import (
    resolve_periods,
    shopee_m1_full_month_day_count,
    shopee_mtd_day_count,
)


def test_parse_shopee_adgmv_rows():
    rows = [
        ["shopid", "shop_name", "mtd_adgmv_usd", "m_1_adgmv_usd"],
        ["1", "Mumu PH", "100.5", "80"],
        ["2", "  Sklyer  ", "10", "5"],
        ["3", "mumu ph", "999", "1"],
    ]
    result = parse_shopee_adgmv_rows(rows, tab="shopee adgmv raw data")
    assert result.stats.total_rows_read == 3
    assert result.stats.total_loaded == 2
    assert result.by_shop_name["mumu ph"].mtd_adgmv_usd == 100.5
    assert result.by_shop_name["sklyer"].tracker_shop_name == "Sklyer"


def test_shopee_day_counts_for_july_23():
    periods = resolve_periods(date(2026, 7, 23))
    assert shopee_mtd_day_count(periods) == 22  # 7/1→7/22
    assert shopee_m1_full_month_day_count(periods) == 30  # June full month


def test_shopee_totals_to_adgmv_and_mom():
    periods = resolve_periods(date(2026, 7, 23))
    # MTD total 220 over 22 days → 10 ADGMV; M-1 total 300 over June 30 → 10 ADGMV
    out = shopee_period_totals_to_adgmv(220.0, 300.0, periods)
    assert out["shopee_mtd_adgmv_usd"] == 10.0
    assert out["shopee_m1_adgmv_usd"] == 10.0
    assert out["shopee_mtd_day_count"] == 22
    assert out["shopee_m1_day_count"] == 30
    assert mom_percent(out["shopee_mtd_adgmv_usd"], out["shopee_m1_adgmv_usd"]) == 0.0


def test_build_record_converts_shopee_totals_to_daily_adgmv():
    periods = resolve_periods(date(2026, 7, 23))
    shopee = ShopeeAdgmvRecord(
        tracker_shop_name="Mumu PH",
        mtd_adgmv_usd=220.0,  # sheet total for MTD window
        m1_adgmv_usd=300.0,  # sheet total for full June
    )
    out = build_business_seller_record(
        shop_id="1",
        shop_name="Mumu PH",
        tiktok_shop_name="Mumu PH",
        mapping_row=None,
        collection_row=None,
        shopee_row=shopee,
        current_periods=periods,
    )
    assert out["shopee_data_status"] == "available"
    assert out["shopee_mtd_total_usd"] == 220.0
    assert out["shopee_m1_total_usd"] == 300.0
    assert out["shopee_mtd_day_count"] == 22
    assert out["shopee_m1_day_count"] == 30
    assert out["shopee_mtd_adgmv_usd"] == 10.0
    assert out["shopee_m1_adgmv_usd"] == 10.0
    assert out["shopee_mom_percent"] == 0.0
    assert out["tracker_shop_name"] == "Mumu PH"
    assert out["tiktok_data_status"] == "na"
    assert out["mtd_shopee_sob_percent"] is None


def test_sob_pair_totals_100_with_daily_adgmv():
    periods = resolve_periods(date(2026, 7, 23))
    # After conversion: Shopee MTD ADGMV = 75/22; TikTok ADGMV PHP already daily
    shopee = ShopeeAdgmvRecord(
        tracker_shop_name="Mumu PH",
        mtd_adgmv_usd=75.0 * 22,
        m1_adgmv_usd=25.0 * 30,
    )
    collection = {
        "status": "success",
        "mtd_gmv_php": 1000,
        "m1_gmv_php": 800,
        "tiktok_mtd_adgmv_php": 6155.0,
        "tiktok_m1_adgmv_php": 6155.0,
        "mtd_start": periods.mtd.start.isoformat(),
        "mtd_end": periods.mtd.end.isoformat(),
        "m1_start": periods.m1.start.isoformat(),
        "m1_end": periods.m1.end.isoformat(),
    }
    with patch(
        "seller.intelligence.business.meta.get_review_by_shop_id",
        return_value={"review_status": "APPROVED"},
    ):
        row = build_business_seller_record(
            shop_id="1",
            shop_name="Mumu PH",
            tiktok_shop_name="Mumu PH",
            mapping_row={"mapping_status": "MAPPED", "tiktok_shop_name": "Mumu PH"},
            collection_row=collection,
            shopee_row=shopee,
            current_periods=periods,
        )
    assert row["shopee_mtd_adgmv_usd"] == 75.0
    assert row["mtd_shopee_sob_percent"] is not None
    assert row["mtd_tiktok_sob_percent"] is not None
    assert abs(row["mtd_shopee_sob_percent"] + row["mtd_tiktok_sob_percent"] - 100.0) <= 0.05
    from seller.intelligence.business.meta import validate_sob_rows

    validation = validate_sob_rows([row])
    assert validation["passed"] is True
