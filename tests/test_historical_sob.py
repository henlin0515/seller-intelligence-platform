"""Historical SOB calculations and sheet parsing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seller.intelligence.historical_sob.portfolio import build_portfolio_historical_sob
from seller.intelligence.historical_sob.service import build_historical_sob_rows
from seller.intelligence.historical_sob.store import save_historical_sob_cache
from seller.intelligence.historical_sob.ytd_monthly import (
    YtdMonthlyRecord,
    parse_ytd_monthly_rows,
)
from seller.intelligence.seller_master import SellerMasterLoadResult, SellerMasterRecord


class YtdMonthlyParseTests(unittest.TestCase):
    def test_parse_columns(self):
        rows = [
            ["shop_name", "shop_id", "ytd_apr_adgmv", "ytd_may_adgmv"],
            ["Shop A", "1001", "100", "200"],
            ["Shop B", "1002", "50.5", "75.25"],
        ]
        result = parse_ytd_monthly_rows(rows)
        self.assertEqual(result.stats.total_loaded, 2)
        rec = result.by_shop_id["1001"]
        self.assertEqual(rec.april_shopee_gmv, 3000.0)
        self.assertEqual(rec.may_shopee_gmv, 6200.0)


class HistoricalSobRowTests(unittest.TestCase):
    def test_sob_requires_both_platforms(self):
        master = SellerMasterLoadResult(
            sellers=[
                SellerMasterRecord("1", "Shop A", "", "TikTok A"),
                SellerMasterRecord("2", "Shop B", "", "TikTok B"),
            ],
            tab="shpoee link",
            data_source="test",
            stats=type("S", (), {"as_dict": lambda self: {}})(),
        )
        ytd = {
            "1": YtdMonthlyRecord("1", "Shop A", 100.0, 100.0),
        }
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
            patch("seller.intelligence.historical_sob.service.get_ytd_monthly") as mock_ytd,
            patch("seller.intelligence.historical_sob.service.load_historical_sob_cache", return_value=cache),
            patch("seller.intelligence.historical_sob.service._mapping_by_shop_id") as mock_map,
            patch("seller.intelligence.historical_sob.service._review_status_for_shop", return_value="APPROVED"),
        ):
            mock_ytd.return_value = type(
                "Y",
                (),
                {"by_shop_id": ytd, "tab": "ytd monthly data", "stats": type("S", (), {"total_loaded": 1})()},
            )()
            mock_map.return_value = {
                "1": {
                    "shop_id": "1",
                    "fastmoss_shop_id": "fm1",
                    "fastmoss_shop_name": "TikTok A",
                    "mapping_status": "MAPPED",
                }
            }
            rows = build_historical_sob_rows(master)

        shop_a = next(r for r in rows if r["shop_id"] == "1")
        shop_b = next(r for r in rows if r["shop_id"] == "2")
        self.assertEqual(shop_a["april_shopee_sob_percent"], 75.0)
        self.assertEqual(shop_a["april_tiktok_sob_percent"], 25.0)
        self.assertIsNone(shop_b["april_shopee_sob_percent"])
        self.assertIsNone(shop_b["april_tiktok_sob_percent"])

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
        self.assertEqual(portfolio["april_shopee_sob_percent"], 75.0)
        self.assertEqual(portfolio["april_tiktok_sob_percent"], 25.0)


class HistoricalSobCacheTests(unittest.TestCase):
    def test_save_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "historical_sob_cache.json"
            save_historical_sob_cache({"shops": {"1": {"status": "success"}}}, path)
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
