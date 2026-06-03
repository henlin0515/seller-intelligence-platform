"""Tests for FastMoss multi-keyword matching (no live API)."""

from __future__ import annotations

import unittest

from seller.fastmoss.mapping import (
    MAPPING_MAPPED,
    MAPPING_NEED_REVIEW,
    MAPPING_NOT_FOUND,
    _decide_status,
    _merge_mapping_row,
    map_seller_to_fastmoss,
)
from seller.fastmoss.match_keywords import generate_search_keywords
from seller.fastmoss.match_scoring import candidate_similarity, rank_candidates
from seller.intelligence.seller_master import SellerMasterRecord


class MatchKeywordsTests(unittest.TestCase):
    def test_fs_store23_variants(self):
        keys = generate_search_keywords("FS.STORE23")
        joined = " ".join(keys).upper()
        self.assertIn("FS.STORE23", keys)
        self.assertTrue(any("FS" in k and "STORE" in k.replace(".", " ") for k in keys) or "FSSTORE23" in joined)

    def test_yoto_shoes_variants(self):
        keys = generate_search_keywords("YOTO SHOES")
        self.assertIn("YOTO SHOES", keys)
        self.assertTrue(any(k.upper() == "YOTO" for k in keys))

    def test_zwb_ph_strips_ph(self):
        keys = generate_search_keywords("ZWB.PH")
        self.assertTrue(any("ZWB" in k for k in keys))


class MatchScoringTests(unittest.TestCase):
    def test_similarity_handle_match(self):
        score = candidate_similarity(
            "FS.STORE23",
            {
                "fastmoss_shop_name": "FS Store 23 Official",
                "fastmoss_handle": "fsstore23",
                "fastmoss_unique_id": "fsstore23",
            },
        )
        self.assertGreaterEqual(score, 0.5)


class DecideStatusTests(unittest.TestCase):
    def test_weak_match_goes_review_not_not_found(self):
        ranked = [{"fastmoss_shop_name": "Similar Shop", "confidence": 0.32}]
        status, match, _ = _decide_status(ranked)
        self.assertEqual(status, MAPPING_NEED_REVIEW)
        self.assertIsNotNone(match)

    def test_high_confidence_mapped(self):
        ranked = [{"fastmoss_shop_name": "YOTO SHOES", "confidence": 0.85}]
        status, _, _ = _decide_status(ranked)
        self.assertEqual(status, MAPPING_MAPPED)


class MergeMappingTests(unittest.TestCase):
    def test_keeps_existing_mapped(self):
        existing = {
            "mapping_status": MAPPING_MAPPED,
            "confidence": 0.9,
            "fastmoss_shop_id": "111",
        }
        new = {"mapping_status": MAPPING_NOT_FOUND, "confidence": 0.0}
        merged = _merge_mapping_row(existing, new)
        self.assertEqual(merged["mapping_status"], MAPPING_MAPPED)

    def test_upgrades_not_found_to_review(self):
        existing = {"mapping_status": MAPPING_NOT_FOUND, "confidence": 0}
        new = {"mapping_status": MAPPING_NEED_REVIEW, "confidence": 0.45, "fastmoss_shop_id": "222"}
        merged = _merge_mapping_row(existing, new)
        self.assertEqual(merged["mapping_status"], MAPPING_NEED_REVIEW)


class MapWithCandidatesTests(unittest.TestCase):
    def test_map_with_candidates_no_api(self):
        seller = SellerMasterRecord(
            shop_id="1",
            shop_name="Test",
            shopee_link="",
            tiktok_shop_name="YOLO SHOES",
        )
        candidates = [
            {
                "fastmoss_shop_id": "99",
                "fastmoss_shop_name": "YOLO SHOES PH",
                "fastmoss_shop_url": "https://example.com/99",
                "fastmoss_handle": "yoloshoes",
            }
        ]
        row = map_seller_to_fastmoss(seller, candidates=candidates)
        self.assertIn(row["mapping_status"], {MAPPING_MAPPED, MAPPING_NEED_REVIEW})
        self.assertGreater(float(row["confidence"] or 0), 0.3)


if __name__ == "__main__":
    unittest.main()
