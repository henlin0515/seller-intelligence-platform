"""Seller Intelligence V1 — unit tests."""

from __future__ import annotations

from datetime import date

from seller.intelligence.business.calculations import (
    build_business_intelligence_record,
    mom_percent,
    sob_pair,
    tiktok_php_to_usd,
)
from seller.intelligence.business.mock_data import get_mock_business_intelligence
from seller.intelligence.config import USD_PHP_RATE
from seller.intelligence.periods import resolve_periods


def test_periods_june_7():
    p = resolve_periods(date(2026, 6, 7))
    assert p.mtd.start == date(2026, 6, 1)
    assert p.mtd.end == date(2026, 6, 6)
    assert p.m1.start == date(2026, 5, 1)
    assert p.m1.end == date(2026, 5, 6)


def test_periods_june_1():
    p = resolve_periods(date(2026, 6, 1))
    assert p.mtd.start == date(2026, 5, 1)
    assert p.mtd.end == date(2026, 5, 31)
    assert p.m1.start == date(2026, 4, 1)
    assert p.m1.end == date(2026, 4, 30)


def test_tiktok_usd_conversion():
    assert tiktok_php_to_usd(6155.0) == 6155.0 / USD_PHP_RATE


def test_mom_formula():
    assert mom_percent(110.0, 100.0) == 10.0


def test_sob_totals_100():
    for record in get_mock_business_intelligence():
        for sk, tk in (
            ("mtd_shopee_sob_percent", "mtd_tiktok_sob_percent"),
            ("m1_shopee_sob_percent", "m1_tiktok_sob_percent"),
        ):
            s, t = record[sk], record[tk]
            if s is not None and t is not None:
                assert abs(s + t - 100.0) < 0.02


def test_calculations_not_hardcoded_in_mock():
    raw = {
        "shop_id": "x",
        "shop_name": "Test",
        "shopee_mtd_adgmv_usd": 100.0,
        "shopee_m1_adgmv_usd": 80.0,
        "tiktok_mtd_adgmv_php": 6155.0,
        "tiktok_m1_adgmv_php": 4924.0,
    }
    out = build_business_intelligence_record(raw)
    assert out["shopee_mom_percent"] == 25.0
    assert out["tiktok_mtd_adgmv_usd"] == 100.0
    assert out["mtd_shopee_sob_percent"] == 50.0
    assert out["mtd_tiktok_sob_percent"] == 50.0
