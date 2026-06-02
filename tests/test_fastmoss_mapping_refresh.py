"""FastMoss mapping refresh helpers."""

from __future__ import annotations

import unittest

from seller.fastmoss.mapping import (
    MAPPING_MAPPED,
    MAPPING_NEED_REVIEW,
    MAPPING_NOT_FOUND,
    should_retry_fastmoss_mapping,
)
from seller.intelligence.seller_master import SellerMasterRecord


def _seller(**kwargs) -> SellerMasterRecord:
    base = {
        "shop_id": "123",
        "shop_name": "Test Shop",
        "shopee_link": "",
        "tiktok_shop_name": "FS.STORE23",
    }
    base.update(kwargs)
    return SellerMasterRecord(**base)


class FastmossMappingRefreshTests(unittest.TestCase):
    def test_should_retry_new_seller(self):
        self.assertTrue(should_retry_fastmoss_mapping(_seller(), None))

    def test_should_not_retry_mapped_without_force(self):
        existing = {"mapping_status": MAPPING_MAPPED, "fastmoss_shop_id": "999"}
        self.assertFalse(should_retry_fastmoss_mapping(_seller(), existing))

    def test_should_retry_not_found(self):
        existing = {"mapping_status": MAPPING_NOT_FOUND}
        self.assertTrue(should_retry_fastmoss_mapping(_seller(), existing))

    def test_should_retry_need_review(self):
        existing = {"mapping_status": MAPPING_NEED_REVIEW}
        self.assertTrue(should_retry_fastmoss_mapping(_seller(), existing))

    def test_should_retry_when_tiktok_name_changed(self):
        existing = {
            "mapping_status": MAPPING_NOT_FOUND,
            "tiktok_shop_name": "OLD NAME",
        }
        self.assertTrue(
            should_retry_fastmoss_mapping(_seller(tiktok_shop_name="FS.STORE23"), existing)
        )

    def test_force_refresh_all_retries_mapped(self):
        existing = {"mapping_status": MAPPING_MAPPED, "fastmoss_shop_id": "999"}
        self.assertTrue(
            should_retry_fastmoss_mapping(_seller(), existing, force_refresh_all=True)
        )


if __name__ == "__main__":
    unittest.main()
