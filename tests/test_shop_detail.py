"""Tests for SLA shop-detail service."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from seller.fastmoss.recent_data import parse_period_metrics
from seller.intelligence.business.shop_detail import (
    UNAVAILABLE_MESSAGE,
    get_shop_detail_payload,
    resolve_detail_date_range,
    shop_detail_available,
)


def test_parse_period_metrics_maps_fastmoss_fields():
    metrics = parse_period_metrics(
        {
            "sold_count": 11800,
            "sale_amount": 1619600.5,
            "author_count": 613,
            "live_count": 172,
            "aweme_count": 449,
            "sold_product_count": 97,
        }
    )
    assert metrics["sales_volume"] == 11800
    assert metrics["sales_amount"] == 1619600.5
    assert metrics["creator_count"] == 613
    assert metrics["live_count"] == 172
    assert metrics["video_count"] == 449
    assert metrics["active_product_count"] == 97


def test_resolve_detail_date_range_defaults_to_seven_days():
    start, end = resolve_detail_date_range(
        start_date=None,
        end_date=date(2026, 6, 15),
    )
    assert end == date(2026, 6, 15)
    assert start == date(2026, 6, 9)


def test_shop_detail_available_rejects_shopee_only():
    assert shop_detail_available({"mapping_status": "MAPPED", "fastmoss_shop_id": "1"}, platform_source="SHOPEE_ONLY") is False


@patch("seller.intelligence.business.shop_detail.fetch_shop_period_metrics")
@patch("seller.intelligence.business.shop_detail.load_fastmoss_mapping")
def test_get_shop_detail_payload_success(mock_mapping, mock_fetch):
    mock_mapping.return_value = {
        "mappings": [
            {
                "shop_id": "123",
                "shop_name": "Demo Shop",
                "mapping_status": "MAPPED",
                "fastmoss_shop_id": "7494609333713275265",
                "fastmoss_shop_name": "Demo TikTok",
            }
        ]
    }
    mock_fetch.return_value = (
        {
            "sales_volume": 100,
            "sales_amount": 200.0,
            "creator_count": 3,
            "live_count": 4,
            "video_count": 5,
            "active_product_count": 6,
        },
        "https://example.test/recentData",
        None,
    )

    payload = get_shop_detail_payload(
        shopee_shop_id="123",
        start_date=date(2026, 6, 9),
        end_date=date(2026, 6, 15),
    )
    assert payload["available"] is True
    assert payload["metrics"]["sales_volume"] == 100
    assert payload["range"]["start_date"] == "2026-06-09"


@patch("seller.intelligence.business.shop_detail.load_fastmoss_mapping")
def test_get_shop_detail_payload_unavailable_without_mapping(mock_mapping):
    mock_mapping.return_value = {"mappings": []}
    payload = get_shop_detail_payload(
        shopee_shop_id="999",
        start_date=date(2026, 6, 9),
        end_date=date(2026, 6, 15),
    )
    assert payload["available"] is False
    assert payload["message"] == UNAVAILABLE_MESSAGE


def test_resolve_detail_date_range_rejects_inverted():
    with pytest.raises(ValueError):
        resolve_detail_date_range(start_date=date(2026, 6, 15), end_date=date(2026, 6, 1))
