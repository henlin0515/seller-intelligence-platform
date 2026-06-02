"""FastMoss mapping review classification and BI gating."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from seller.fastmoss.mapping import MAPPING_MAPPED
from seller.fastmoss.review import (
    REVIEW_APPROVED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    ensure_review_store_synced,
    suggest_review_status,
)


def _mapping_row(**kwargs):
    base = {
        "shop_id": "1",
        "shop_name": "Test",
        "tiktok_shop_name": "Test Shop",
        "fastmoss_shop_name": "Test Shop",
        "mapping_status": MAPPING_MAPPED,
        "confidence": 0.99,
    }
    base.update(kwargs)
    return base


class MappingReviewClassificationTests(unittest.TestCase):
    def test_lala_yoto_rejected(self):
        row = _mapping_row(
            shop_name="LaLa_Shoes.PH",
            tiktok_shop_name="LALA",
            fastmoss_shop_name="YOTO SHOES",
            confidence=0.72,
        )
        status, _reason = suggest_review_status(row)
        self.assertIn(status, {REVIEW_REJECTED, REVIEW_PENDING})
        self.assertNotEqual(status, REVIEW_APPROVED)

    def test_eight_percent_rejected(self):
        row = _mapping_row(
            shop_name="8% STORE Eight Percent",
            tiktok_shop_name="Eight Persent Store",
            fastmoss_shop_name="997 Studio",
            confidence=0.71,
        )
        status, _reason = suggest_review_status(row)
        self.assertIn(status, {REVIEW_REJECTED, REVIEW_PENDING})
        self.assertNotEqual(status, REVIEW_APPROVED)

    def test_skyler_pending(self):
        row = _mapping_row(
            shop_name="Sklyer",
            tiktok_shop_name="Skyler Shop",
            fastmoss_shop_name="Skyler shop8",
            confidence=0.88,
        )
        status, _reason = suggest_review_status(row)
        self.assertEqual(status, REVIEW_PENDING)

    def test_mumu_exact_approved(self):
        row = _mapping_row(
            shop_name="Mumu PH",
            tiktok_shop_name="Mumu PH",
            fastmoss_shop_name="Mumu PH",
            confidence=0.99,
        )
        status, _reason = suggest_review_status(row)
        self.assertEqual(status, REVIEW_APPROVED)


class MappingReviewBiGatingTests(unittest.TestCase):
    @patch(
        "seller.intelligence.business.meta.get_review_by_shop_id",
        return_value={"review_status": REVIEW_REJECTED},
    )
    def test_rejected_review_hides_tiktok_data(self, _mock_review):
        from seller.intelligence.business.meta import build_business_seller_record

        record = build_business_seller_record(
            shop_id="64329852",
            shop_name="LaLa_Shoes.PH",
            tiktok_shop_name="LALA",
            mapping_row=_mapping_row(
                shop_id="64329852",
                tiktok_shop_name="LALA",
                fastmoss_shop_name="YOTO SHOES",
            ),
            collection_row={
                "status": "success",
                "mtd_gmv_php": 1000,
                "m1_gmv_php": 900,
                "tiktok_mtd_adgmv_php": 50,
                "tiktok_m1_adgmv_php": 45,
            },
        )
        self.assertEqual(record["tiktok_data_status"], "na")
        self.assertIsNone(record["tiktok_mtd_adgmv_usd"])
        self.assertIsNone(record["mtd_tiktok_sob_percent"])


class MappingReviewSyncTests(unittest.TestCase):
    def test_ensure_review_store_synced_from_empty(self):
        mappings = [
            _mapping_row(
                shop_id="1",
                shop_name="Mumu PH",
                tiktok_shop_name="Mumu PH",
                fastmoss_shop_name="Mumu PH",
            )
        ]
        with (
            patch("seller.fastmoss.review.load_mapping_rows_for_review", return_value=mappings),
            patch(
                "seller.fastmoss.review.load_review_store",
                return_value={"version": 1, "updated_at": None, "reviews": {}},
            ),
            patch("seller.fastmoss.review.save_review_store", side_effect=lambda payload, path=None: payload),
        ):
            result = ensure_review_store_synced(force=True)
        self.assertEqual(len(result.get("reviews") or {}), 1)
        self.assertEqual(result["reviews"]["1"]["review_status"], REVIEW_APPROVED)


if __name__ == "__main__":
    unittest.main()
