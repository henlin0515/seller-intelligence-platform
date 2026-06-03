"""Historical SOB calculations and sheet parsing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seller.intelligence.business.calculations import sob_pair, tiktok_php_to_usd
from seller.intelligence.config import USD_PHP_RATE
from seller.intelligence.historical_sob.portfolio import build_portfolio_historical_sob
from seller.intelligence.historical_sob.service import build_historical_sob_rows, get_historical_sob_payload
from seller.intelligence.historical_sob.store import save_historical_sob_cache
from seller.intelligence.historical_sob.ytd_monthly import (
    YtdMonthlyLoadResult,
    YtdMonthlyRecord,
    lookup_ytd_record,
    normalize_shop_name,
    parse_ytd_monthly_rows,
    resolve_ytd_monthly_tab_title,
    _header_row_has_ytd_columns,
)
from seller.intelligence.seller_master import (
    SellerMasterImportStats,
    SellerMasterLoadResult,
    SellerMasterRecord,
)


def _ytd_result(records: list[YtdMonthlyRecord]) -> YtdMonthlyLoadResult:
    by_name = {normalize_shop_name(r.shop_name): r for r in records}
    by_id = {r.shop_id: r for r in records if r.shop_id}
    return YtdMonthlyLoadResult(
        by_shop_name=by_name,
        by_shop_id=by_id,
        stats=type("S", (), {"total_loaded": len(by_name), "total_rows_read": len(records)})(),
        tab="ytd monthly data",
        data_source="test",
    )


class YtdMonthlyParseTests(unittest.TestCase):
    def test_parse_ytd_apr_adgmv_column(self):
        rows = [
            ["shop_name", "shop_id", "ytd_apr_adgmv", "ytd_may_adgmv"],
            ["Shop A", "1001", "100", "200"],
            ["Shop B", "", "50.5", "75.25"],
        ]
        result = parse_ytd_monthly_rows(rows)
        self.assertEqual(result.stats.total_loaded, 2)
        rec = result.by_shop_name[normalize_shop_name("Shop A")]
        self.assertEqual(rec.april_shopee_gmv, 3000.0)
        self.assertEqual(rec.may_shopee_gmv, 6200.0)
        partial = result.by_shop_name[normalize_shop_name("Shop B")]
        self.assertEqual(partial.april_shopee_gmv, 1515.0)
        self.assertEqual(partial.may_shopee_gmv, 2332.75)

    def test_match_by_shop_id_primary(self):
        rows = [
            ["shop_name", "shop_id", "ytd_apr_adgmv", "ytd_may_adgmv"],
            ["Wrong Name", "64329852", "10", "20"],
        ]
        ytd = parse_ytd_monthly_rows(rows)
        rec = lookup_ytd_record(ytd, shop_name="LaLa_Shoes.PH", shop_id="64329852")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.april_shopee_gmv, 300.0)

    def test_match_by_shop_name_fallback(self):
        rows = [
            ["shop_name", "shop_id", "ytd_apr_adgmv", "ytd_may_adgmv"],
            ["LaLa_Shoes.PH", "DIFFERENT_ID", "10", "20"],
        ]
        ytd = parse_ytd_monthly_rows(rows)
        rec = lookup_ytd_record(ytd, shop_name="LaLa_Shoes.PH", shop_id="64329852")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.april_shopee_gmv, 300.0)

    def test_resolve_ytd_tab_title_case_insensitive(self):
        titles = ["AI data", "YTD Monthly Data", "shpoee link"]
        self.assertEqual(
            resolve_ytd_monthly_tab_title(titles, "ytd monthly data"),
            "YTD Monthly Data",
        )

    def test_header_row_detects_ytd_columns(self):
        header = ["shop_name", "shop_id", "ytd_apr_adgmv", "ytd_may_adgmv"]
        self.assertTrue(_header_row_has_ytd_columns(header))
        self.assertFalse(_header_row_has_ytd_columns(["shop_name", "shop_id", "other"]))


class HistoricalSobRowTests(unittest.TestCase):
    def _master(self) -> SellerMasterLoadResult:
        return SellerMasterLoadResult(
            sellers=[
                SellerMasterRecord("1", "Shop A", "", "TikTok A"),
                SellerMasterRecord("2", "Shop B", "", "TikTok B"),
            ],
            tab="shpoee link",
            data_source="test",
            stats=SellerMasterImportStats(),
        )

    def test_sob_requires_both_platforms(self):
        master = self._master()
        ytd = _ytd_result([YtdMonthlyRecord("", "Shop A", 100.0, 100.0)])
        cache = {
            "shops": {
                "1": {
                    "status": "success",
                    "april_gmv_php": 1000.0,
                    "may_gmv_php": 2000.0,
                }
            }
        }

        with (
            patch("seller.intelligence.historical_sob.service.get_ytd_monthly", return_value=ytd),
            patch("seller.intelligence.historical_sob.service.load_historical_sob_cache", return_value=cache),
            patch("seller.intelligence.historical_sob.service._fastmoss_mapping_indexes") as mock_map,
            patch(
                "seller.intelligence.historical_sob.service.get_review_by_shop_id",
                return_value={"review_status": "APPROVED"},
            ),
        ):
            mock_map.return_value = (
                {
                    "1": {
                        "shop_id": "1",
                        "fastmoss_shop_id": "fm1",
                        "fastmoss_shop_name": "TikTok A",
                        "mapping_status": "MAPPED",
                    }
                },
                {},
            )
            rows = build_historical_sob_rows(master, ytd=ytd, tiktok_cache=cache)

        shop_a = next(r for r in rows if r["shop_id"] == "1")
        shop_b = next(r for r in rows if r["shop_id"] == "2")
        april_shopee = 3000.0
        may_shopee = 3100.0
        april_tiktok_usd = round(tiktok_php_to_usd(1000.0), 2)
        may_tiktok_usd = round(tiktok_php_to_usd(2000.0), 2)
        _, expected_april_tiktok_sob = sob_pair(april_shopee, april_tiktok_usd)
        _, expected_may_tiktok_sob = sob_pair(may_shopee, may_tiktok_usd)
        self.assertEqual(shop_a["april_shopee_gmv"], april_shopee)
        self.assertEqual(shop_a["april_tiktok_gmv"], april_tiktok_usd)
        self.assertEqual(shop_a["may_tiktok_gmv"], may_tiktok_usd)
        self.assertEqual(shop_a["april_sob_percent"], round(expected_april_tiktok_sob, 1))
        self.assertEqual(shop_a["may_sob_percent"], round(expected_may_tiktok_sob, 1))
        self.assertIsNone(shop_b["april_sob_percent"])
        self.assertIsNotNone(shop_b["shopee_na_reason"])

    def test_tiktok_php_converted_to_usd_for_display_and_sob(self):
        php = 1_314_253.0
        expected_usd = round(php / USD_PHP_RATE, 2)
        self.assertEqual(expected_usd, 21352.61)
        master = self._master()
        ytd = _ytd_result([YtdMonthlyRecord("1", "Shop A", 10.0, 10.0)])
        cache = {
            "shops": {
                "1": {
                    "status": "success",
                    "april_gmv_php": php,
                    "may_gmv_php": php,
                }
            }
        }
        with (
            patch("seller.intelligence.historical_sob.service.get_ytd_monthly", return_value=ytd),
            patch("seller.intelligence.historical_sob.service.load_historical_sob_cache", return_value=cache),
            patch("seller.intelligence.historical_sob.service._fastmoss_mapping_indexes") as mock_map,
            patch(
                "seller.intelligence.historical_sob.service.get_review_by_shop_id",
                return_value={"review_status": "APPROVED"},
            ),
        ):
            mock_map.return_value = (
                {
                    "1": {
                        "shop_id": "1",
                        "fastmoss_shop_id": "fm1",
                        "mapping_status": "MAPPED",
                    }
                },
                {},
            )
            rows = build_historical_sob_rows(master, ytd=ytd, tiktok_cache=cache)
        shop_a = next(r for r in rows if r["shop_id"] == "1")
        self.assertEqual(shop_a["april_tiktok_gmv"], expected_usd)

    def test_portfolio_aggregate(self):
        rows = [
            {
                "april_shopee_gmv": 3000.0,
                "april_tiktok_gmv": 1000.0,
                "may_shopee_gmv": 3100.0,
                "may_tiktok_gmv": 900.0,
            },
            {
                "april_shopee_gmv": 6000.0,
                "april_tiktok_gmv": 2000.0,
                "may_shopee_gmv": 6200.0,
                "may_tiktok_gmv": 1800.0,
            },
        ]
        portfolio = build_portfolio_historical_sob(rows)
        self.assertEqual(portfolio["april_shopee_gmv"], 9000.0)
        self.assertEqual(portfolio["april_tiktok_gmv"], 3000.0)
        self.assertEqual(portfolio["april_portfolio_sob_percent"], 25.0)

    def test_payload_never_raises_on_ytd_error(self):
        master = self._master()
        ytd = YtdMonthlyLoadResult(
            by_shop_name={},
            by_shop_id={},
            stats=type("S", (), {"total_loaded": 0})(),
            tab="ytd monthly data",
            data_source="unavailable",
            load_error="Worksheet not found",
        )
        with (
            patch("seller.intelligence.historical_sob.service.get_seller_master", return_value=master),
            patch("seller.intelligence.historical_sob.service.get_ytd_monthly", return_value=ytd),
            patch("seller.intelligence.historical_sob.service.load_historical_sob_cache", return_value={"shops": {}}),
            patch("seller.intelligence.historical_sob.service._fastmoss_mapping_indexes", return_value=({}, {})),
            patch("seller.intelligence.historical_sob.service.refresh_historical_sob_tiktok_cache", return_value={}),
        ):
            payload = get_historical_sob_payload(master, ensure_tiktok_cache=False)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["warnings"])
        self.assertEqual(len(payload["sellers"]), 2)
        self.assertEqual(payload["master_currency"], "USD")
        self.assertEqual(payload["shopee_currency"], "USD")
        self.assertEqual(payload["tiktok_source_currency"], "PHP")
        self.assertEqual(payload["usd_php_rate"], USD_PHP_RATE)


    def test_fastmoss_mapped_without_review_shows_mapped(self):
        master = self._master()
        ytd = _ytd_result([YtdMonthlyRecord("", "Shop A", 10.0, 10.0)])
        with (
            patch("seller.intelligence.historical_sob.service.get_ytd_monthly", return_value=ytd),
            patch("seller.intelligence.historical_sob.service.load_historical_sob_cache", return_value={"shops": {}}),
            patch("seller.intelligence.historical_sob.service._fastmoss_mapping_indexes") as mock_map,
            patch("seller.intelligence.historical_sob.service.get_review_by_shop_id", return_value=None),
        ):
            mock_map.return_value = (
                {},
                {
                    "shop a": {
                        "shop_id": "99",
                        "shop_name": "Shop A",
                        "mapping_status": "MAPPED",
                    }
                },
            )
            rows = build_historical_sob_rows(master, ytd=ytd, tiktok_cache={"shops": {}})
        shop_a = next(r for r in rows if r["shop_id"] == "1")
        self.assertEqual(shop_a["fastmoss_match_status"], "MAPPED")


class HistoricalSobCacheTests(unittest.TestCase):
    def test_save_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "historical_sob_cache.json"
            save_historical_sob_cache({"shops": {"1": {"status": "success"}}}, path)
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
