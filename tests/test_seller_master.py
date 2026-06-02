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


def test_seller_master_cache_ttl_refreshes_after_expiry():
    from unittest.mock import patch

    from seller.intelligence import seller_master as sm

    sm.clear_seller_master_cache()
    rows = [["123", "Alpha Shop", "https://shopee.ph/alpha", "Alpha TT"]]
    parsed = parse_shpoee_link_rows(rows)

    with patch.object(sm, "SELLER_MASTER_CACHE_TTL_SEC", 300):
        with patch.object(sm, "is_configured", return_value=True):
            with patch.object(sm, "get_sheets_client") as mock_client:
                mock_client.return_value.fetch_worksheet_values.return_value = [
                    ["Shop ID", "Shop Name", "Shopee Link", "TikTok Shop Name"],
                    *rows,
                ]
                t0 = 1_000_000.0
                with patch.object(sm.time, "time", side_effect=[t0, t0 + 1, t0 + 301, t0 + 302]):
                    first = sm.load_seller_master_from_sheet()
                    second = sm.load_seller_master_from_sheet()
                    third = sm.load_seller_master_from_sheet()

    assert first.stats.total_loaded == 1
    assert second is first
    assert third is not first
    assert mock_client.return_value.fetch_worksheet_values.call_count == 2
    sm.clear_seller_master_cache()
