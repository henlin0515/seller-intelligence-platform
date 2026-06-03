"""GP SHOP AND RM RAW parser and RM filter matching."""

from __future__ import annotations

import unittest

from seller.intelligence.gp_shop_rm import (
    ALL_GP_VALUE,
    ALL_RM_VALUE,
    GpShopRmIndex,
    normalize_shop_key,
    parse_gp_shop_rm_rows,
    seller_matches_gp,
    seller_matches_rm,
)


class GpShopRmTests(unittest.TestCase):
    def test_parse_forward_fill_rm_and_gp(self):
        rows = [
            ["RM", "GP NAME", "SHOP NAME"],
            ["linda.wu@shopee.com", "Mumu PH", "Mumu PH"],
            ["", "", "MUMUSELECT PH"],
            ["", "", "LYX SHOP"],
            ["", "UISN Mall", "UISN Mall"],
            ["", "", "yoyo bags"],
        ]
        index = parse_gp_shop_rm_rows(rows)
        self.assertIn("linda.wu@shopee.com", index.by_rm)
        names = index.by_rm["linda.wu@shopee.com"]
        self.assertIn(normalize_shop_key("Mumu PH"), names)
        self.assertIn(normalize_shop_key("MUMUSELECT PH"), names)
        self.assertIn(normalize_shop_key("UISN Mall"), names)
        self.assertIn(normalize_shop_key("yoyo bags"), names)

    def test_normalize_trim_and_case(self):
        self.assertEqual(normalize_shop_key("  ZWB.PH  "), "zwb.ph")

    def test_seller_matches_rm_all(self):
        index = GpShopRmIndex(
            tab="t",
            by_rm={"rm1": {normalize_shop_key("Shop A")}},
        )
        self.assertTrue(
            seller_matches_rm(shop_name="Shop A", rm_value=ALL_RM_VALUE, index=index)
        )
        self.assertTrue(
            seller_matches_rm(shop_name="Unknown", rm_value=ALL_RM_VALUE, index=index)
        )

    def test_seller_matches_rm_specific(self):
        index = GpShopRmIndex(
            tab="t",
            by_rm={
                "rm1": {normalize_shop_key("Shop A"), normalize_shop_key("GP Alias")},
            },
        )
        self.assertTrue(
            seller_matches_rm(shop_name="shop a", rm_value="rm1", index=index)
        )
        self.assertTrue(
            seller_matches_rm(shop_name="GP Alias", rm_value="rm1", index=index)
        )
        self.assertFalse(
            seller_matches_rm(shop_name="Other Shop", rm_value="rm1", index=index)
        )

    def test_unmapped_hidden_when_rm_selected(self):
        index = GpShopRmIndex(tab="t", by_rm={"rm1": {normalize_shop_key("Mapped")}})
        self.assertFalse(
            seller_matches_rm(shop_name="Not In Sheet", rm_value="rm1", index=index)
        )

    def test_parse_by_gp_shop_names_only(self):
        rows = [
            ["RM", "GP NAME", "SHOP NAME"],
            ["linda.wu@shopee.com", "Mumu PH", "Mumu PH"],
            ["", "", "MUMUSELECT PH"],
            ["", "UISN Mall", "UISN Mall"],
            ["", "", "yoyo bags"],
        ]
        index = parse_gp_shop_rm_rows(rows)
        self.assertIn("Mumu PH", index.by_gp)
        mumu = index.by_gp["Mumu PH"]
        self.assertIn(normalize_shop_key("Mumu PH"), mumu)
        self.assertIn(normalize_shop_key("MUMUSELECT PH"), mumu)
        uisn = index.by_gp["UISN Mall"]
        self.assertIn(normalize_shop_key("UISN Mall"), uisn)
        self.assertIn(normalize_shop_key("yoyo bags"), uisn)
        self.assertNotIn(normalize_shop_key("Mumu PH"), uisn)

    def test_gp_filter_payload_options(self):
        index = parse_gp_shop_rm_rows(
            [
                ["RM", "GP NAME", "SHOP NAME"],
                ["rm", "GP A", "Shop One"],
            ]
        )
        payload = index.gp_filter_payload()
        values = [o["value"] for o in payload["options"]]
        self.assertEqual(values[0], ALL_GP_VALUE)
        self.assertIn("GP A", values)

    def test_seller_matches_gp_specific(self):
        index = GpShopRmIndex(
            tab="t",
            by_gp={"GP A": {normalize_shop_key("Shop One")}},
        )
        self.assertTrue(
            seller_matches_gp(shop_name="shop one", gp_value="GP A", index=index)
        )
        self.assertFalse(
            seller_matches_gp(shop_name="Other", gp_value="GP A", index=index)
        )

    def test_rm_and_gp_combined_matching(self):
        rows = [
            ["RM", "GP NAME", "SHOP NAME"],
            ["rm1", "GP A", "Shop A"],
            ["", "GP B", "Shop B"],
        ]
        index = parse_gp_shop_rm_rows(rows)
        self.assertTrue(
            seller_matches_rm(shop_name="Shop A", rm_value="rm1", index=index)
            and seller_matches_gp(shop_name="Shop A", gp_value="GP A", index=index)
        )
        self.assertFalse(
            seller_matches_rm(shop_name="Shop B", rm_value="rm1", index=index)
            and seller_matches_gp(shop_name="Shop B", gp_value="GP A", index=index)
        )


if __name__ == "__main__":
    unittest.main()
