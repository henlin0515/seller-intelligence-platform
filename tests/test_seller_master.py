"""Unit tests for seller master parsing (Phase 1)."""

from __future__ import annotations

from seller.intelligence.seller_master import parse_shpoee_link_rows


def test_parse_header_and_valid_rows():
    rows = [
        ["Shop ID", "Shop Name", "Shopee Link", "TikTok Shop Name"],
        ["123", "Alpha Shop", "https://shopee.ph/alpha", "Alpha TT"],
        ["456", "Beta Shop", "https://shopee.ph/beta", ""],
    ]
    result = parse_shpoee_link_rows(rows)
    assert result.stats.total_rows_read == 2
    assert result.stats.total_loaded == 2
    assert len(result.stats.failed_rows) == 0
    assert result.stats.missing_tiktok_shop_names == ["456"]
    assert result.sellers[0].shop_id == "123"
    assert result.sellers[1].tiktok_shop_name == ""


def test_parse_duplicate_and_missing_shop_id():
    rows = [
        ["111", "First", "https://shopee.ph/first", "TT1"],
        ["111", "Duplicate", "https://shopee.ph/dup", "TT dup"],
        ["", "No ID", "https://shopee.ph/noid", "TT2"],
        ["222", "", "https://shopee.ph/noname", "TT3"],
    ]
    result = parse_shpoee_link_rows(rows)
    assert result.stats.total_loaded == 1
    assert result.stats.duplicate_shop_ids == ["111"]
    assert any(f["reason"] == "missing_shop_id" for f in result.stats.failed_rows)
    assert any(f["reason"] == "missing_shop_name" for f in result.stats.failed_rows)


def test_parse_empty_row_fails():
    rows = [["999", "Ok", "https://shopee.ph/ok", "TT"], ["", "", "", ""]]
    result = parse_shpoee_link_rows(rows)
    assert result.stats.total_loaded == 1
    assert any(f["reason"] == "empty_row" for f in result.stats.failed_rows)
