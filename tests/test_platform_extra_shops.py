"""Shopee-only and TikTok-only sheet parsers for Seller Level Analysis."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from seller.intelligence.business.meta import build_merged_business_seller_rows
from seller.intelligence.business.shopee_adgmv import ShopeeAdgmvRecord
from seller.intelligence.platform_extra_shops import (
    ShopeeShopOnlyLoadResult,
    ShopeeShopOnlyRecord,
    TiktokShopOnlyLoadResult,
    parse_shopee_shop_only_rows,
    parse_tiktok_shop_only_rows,
)
from seller.intelligence.seller_master import (
    SellerMasterImportStats,
    SellerMasterLoadResult,
    SellerMasterRecord,
)


class PlatformExtraShopsParseTests(unittest.TestCase):
    def test_parse_shopee_shop_only(self):
        rows = [
            ["GP Shop ID", "GP Shop Name", "Shop ID", "shopee shop name", "RM"],
            ["20225575", "Eat Toi jeans", "45528205", "ZORRA FASHION", "hoeglin.chen@shopee.com"],
        ]
        result = parse_shopee_shop_only_rows(rows)
        self.assertEqual(result.stats["total_loaded"], 1)
        rec = result.rows[0]
        self.assertEqual(rec.shop_id, "45528205")
        self.assertEqual(rec.shop_name, "ZORRA FASHION")
        self.assertEqual(rec.gp_shop_name, "Eat Toi jeans")
        self.assertEqual(rec.rm, "hoeglin.chen@shopee.com")

    def test_parse_tiktok_shop_only(self):
        rows = [
            ["GP Shop ID", "GP Shop Name", "TikTok shop name"],
            ["99", "Aya shop", "YD Trend.PH"],
        ]
        result = parse_tiktok_shop_only_rows(rows)
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0].tiktok_shop_name, "YD Trend.PH")
        self.assertTrue(result.rows[0].synthetic_shop_id.startswith("tkonly:"))


class MergedBusinessRowsTests(unittest.TestCase):
    def test_shopee_only_sob_100_shopee(self):
        master = SellerMasterLoadResult(
            sellers=[],
            tab="shpoee link",
            data_source="test",
            stats=SellerMasterImportStats(),
        )
        shopee_only = ShopeeShopOnlyLoadResult(
            rows=[
                ShopeeShopOnlyRecord(
                    gp_shop_id="1",
                    gp_shop_name="GP A",
                    shop_id="100",
                    shop_name="Only Shopee",
                    rm="rm@test.com",
                )
            ],
            tab="shopee shop only",
            data_source="test",
        )
        tiktok_only = TiktokShopOnlyLoadResult(rows=[], tab="tiktok shop only", data_source="test")

        tracker = type(
            "T",
            (),
            {
                "by_shop_name": {
                    "only shopee": ShopeeAdgmvRecord(
                        tracker_shop_name="Only Shopee",
                        mtd_adgmv_usd=500.0,
                        m1_adgmv_usd=400.0,
                    )
                },
                "tab": "tracker",
            },
        )()

        with (
            patch(
                "seller.intelligence.business.meta.try_load_platform_extra_shops",
                return_value=(shopee_only, tiktok_only),
            ),
            patch("seller.intelligence.business.meta.load_business_intelligence_data", return_value=None),
            patch("seller.intelligence.business.meta._fastmoss_mapping_indexes", return_value=({}, {})),
            patch("seller.intelligence.business.meta.get_shopee_adgmv", return_value=tracker),
            patch(
                "seller.intelligence.business.meta.match_shopee_adgmv_to_shop_name",
                side_effect=lambda name, _t: tracker.by_shop_name.get((name or "").strip().casefold()),
            ),
        ):
            rows = build_merged_business_seller_rows(master, shopee_adgmv=tracker)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["platform_source"], "SHOPEE_ONLY")
        self.assertEqual(row["mtd_shopee_sob_percent"], 100.0)
        self.assertEqual(row["mtd_tiktok_sob_percent"], 0.0)
        self.assertIsNone(row["tiktok_mtd_adgmv_usd"])


if __name__ == "__main__":
    unittest.main()
