"""category raw sheet parser."""

from __future__ import annotations

import unittest

from seller.intelligence.category_raw import parse_category_raw_rows
from seller.intelligence.gp_shop_rm import normalize_shop_key


class CategoryRawTests(unittest.TestCase):
    def test_parse_four_category_columns(self):
        rows = [
            ["Women's Bags", "Shoes", "Men's Apparel", "Women's Apparel"],
            ["Mumu PH", "MIA SHOES", "K M SHOP", "ecoraph"],
            ["MUMUSELECT PH", "Skyer", "", "Rhian"],
            ["", "JULYYA SHOES", "JKS shop", ""],
        ]
        index = parse_category_raw_rows(rows)
        self.assertEqual(len(index.categories), 4)
        bags = index.by_category["Women's Bags"]
        self.assertIn(normalize_shop_key("Mumu PH"), bags)
        self.assertIn(normalize_shop_key("MUMUSELECT PH"), bags)
        shoes = index.by_category["Shoes"]
        self.assertIn(normalize_shop_key("MIA SHOES"), shoes)
        self.assertNotIn(normalize_shop_key("Mumu PH"), shoes)

    def test_normalize_trim_case(self):
        rows = [
            ["Cat A", "", "", ""],
            ["  ZWB.PH  ", "", "", ""],
        ]
        index = parse_category_raw_rows(rows)
        keys = index.by_category["Cat A"]
        self.assertEqual(keys, ["zwb.ph"])


if __name__ == "__main__":
    unittest.main()
