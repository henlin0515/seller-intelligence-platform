"""Seller Level Analysis refresh job helpers."""

from __future__ import annotations

import unittest

from seller.intelligence.business.sla_refresh import STEPS, _categorize_sellers
from seller.intelligence.seller_master import SellerMasterRecord


def _seller(**kwargs) -> SellerMasterRecord:
    base = {
        "shop_id": "1",
        "shop_name": "Shop A",
        "shopee_link": "",
        "tiktok_shop_name": "YOTO Sandals",
    }
    base.update(kwargs)
    return SellerMasterRecord(**base)


class SlaRefreshTests(unittest.TestCase):
    def test_steps_count(self):
        self.assertEqual(len(STEPS), 9)
        self.assertEqual(STEPS[0][0], "seller_master")

    def test_categorize_not_found_and_preserved(self):
        sellers = [
            _seller(shop_id="1", tiktok_shop_name="YOTO Sandals"),
            _seller(shop_id="2", tiktok_shop_name="Mapped Shop"),
        ]
        existing = {
            "1": {"shop_id": "1", "mapping_status": "NOT_FOUND", "tiktok_shop_name": "YOTO Sandals"},
            "2": {
                "shop_id": "2",
                "mapping_status": "MAPPED",
                "tiktok_shop_name": "Mapped Shop",
                "fastmoss_shop_id": "99",
            },
        }
        nf, pending, preserved, changed = _categorize_sellers(sellers, existing)
        self.assertEqual(len(nf), 1)
        self.assertEqual(len(pending), 0)
        self.assertEqual(preserved, 1)
        self.assertEqual(changed, 0)

    def test_categorize_need_review(self):
        sellers = [_seller(shop_id="3", tiktok_shop_name="Review Me")]
        existing = {
            "3": {"shop_id": "3", "mapping_status": "NEED_REVIEW", "tiktok_shop_name": "Review Me"},
        }
        nf, pending, preserved, changed = _categorize_sellers(sellers, existing)
        self.assertEqual(len(nf), 0)
        self.assertEqual(len(pending), 1)
        self.assertEqual(preserved, 0)


if __name__ == "__main__":
    unittest.main()
