"""Shopee ADGMV Tracker import tests."""

from __future__ import annotations

from seller.intelligence.business.meta import build_business_seller_record
from seller.intelligence.business.shopee_adgmv import (
    ShopeeAdgmvRecord,
    parse_shopee_adgmv_rows,
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


def test_build_record_applies_shopee_without_touching_tiktok():
    shopee = ShopeeAdgmvRecord(
        tracker_shop_name="Mumu PH",
        mtd_adgmv_usd=100.0,
        m1_adgmv_usd=80.0,
    )
    out = build_business_seller_record(
        shop_id="1",
        shop_name="Mumu PH",
        tiktok_shop_name="Mumu PH",
        mapping_row=None,
        collection_row=None,
        shopee_row=shopee,
    )
    assert out["shopee_data_status"] == "available"
    assert out["shopee_mtd_adgmv_usd"] == 100.0
    assert out["shopee_m1_adgmv_usd"] == 80.0
    assert out["tracker_shop_name"] == "Mumu PH"
    assert out["tiktok_data_status"] == "na"
    assert out["mtd_shopee_sob_percent"] is None


def test_sob_pair_totals_100():
    from seller.intelligence.business.meta import build_business_seller_record, validate_sob_rows
    from seller.intelligence.business.shopee_adgmv import ShopeeAdgmvRecord

    shopee = ShopeeAdgmvRecord(tracker_shop_name="Mumu PH", mtd_adgmv_usd=75.0, m1_adgmv_usd=25.0)
    collection = {
        "status": "success",
        "mtd_gmv_php": 1000,
        "m1_gmv_php": 800,
        "tiktok_mtd_adgmv_php": 6155.0,
        "tiktok_m1_adgmv_php": 6155.0,
    }
    row = build_business_seller_record(
        shop_id="1",
        shop_name="Mumu PH",
        tiktok_shop_name="Mumu PH",
        mapping_row={"mapping_status": "MAPPED"},
        collection_row=collection,
        shopee_row=shopee,
    )
    assert row["mtd_shopee_sob_percent"] is not None
    assert row["mtd_tiktok_sob_percent"] is not None
    assert abs(row["mtd_shopee_sob_percent"] + row["mtd_tiktok_sob_percent"] - 100.0) <= 0.05
    validation = validate_sob_rows([row])
    assert validation["passed"] is True
