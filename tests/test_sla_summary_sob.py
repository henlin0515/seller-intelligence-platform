"""Seller Level Analysis summary SOB — GMV totals, not row SOB averages."""

from __future__ import annotations

import unittest

from seller.intelligence.business.calculations import aggregate_sob_from_rows


class SlaSummarySobTests(unittest.TestCase):
    def test_aggregate_sob_from_gmv_totals_mixed_platforms(self):
        """Example from spec: 100/100 normal, 50/0 shopee-only, 0/50 tiktok-only => 50/50 SOB."""
        rows = [
            {
                "shop_name": "A",
                "shopee_mtd_adgmv_usd": 100,
                "tiktok_mtd_adgmv_usd": 100,
                "mtd_shopee_sob_percent": 50.0,
                "mtd_tiktok_sob_percent": 50.0,
            },
            {
                "shop_name": "B",
                "platform_source": "SHOPEE_ONLY",
                "shopee_mtd_adgmv_usd": 50,
                "tiktok_mtd_adgmv_usd": None,
                "mtd_shopee_sob_percent": 100.0,
                "mtd_tiktok_sob_percent": 0.0,
            },
            {
                "shop_name": "C",
                "platform_source": "TIKTOK_ONLY",
                "shopee_mtd_adgmv_usd": None,
                "tiktok_mtd_adgmv_usd": 50,
                "mtd_shopee_sob_percent": 0.0,
                "mtd_tiktok_sob_percent": 100.0,
            },
        ]
        agg = aggregate_sob_from_rows(rows)
        self.assertEqual(agg["shopee_gmv_usd"], 150.0)
        self.assertEqual(agg["tiktok_gmv_usd"], 150.0)
        self.assertEqual(agg["shopee_sob_percent"], 50.0)
        self.assertEqual(agg["tiktok_sob_percent"], 50.0)

    def test_missing_gmv_counts_as_zero(self):
        rows = [
            {"shopee_mtd_adgmv_usd": 80, "tiktok_mtd_adgmv_usd": None},
            {"shopee_mtd_adgmv_usd": None, "tiktok_mtd_adgmv_usd": 20},
        ]
        agg = aggregate_sob_from_rows(rows)
        self.assertEqual(agg["shopee_sob_percent"], 80.0)
        self.assertEqual(agg["tiktok_sob_percent"], 20.0)

    def test_empty_scope_returns_na(self):
        agg = aggregate_sob_from_rows([])
        self.assertIsNone(agg["shopee_sob_percent"])
        self.assertIsNone(agg["tiktok_sob_percent"])


if __name__ == "__main__":
    unittest.main()
