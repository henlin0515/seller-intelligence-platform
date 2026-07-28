from __future__ import annotations

from datetime import date
from unittest.mock import patch

from seller.intelligence.fastmoss_shop_search import get_fastmoss_shop_detail, search_fastmoss_shops


@patch("seller.intelligence.fastmoss_shop_search.search_shops_or_raise")
def test_search_fastmoss_shops_returns_ranked_candidates(mock_search):
    mock_search.return_value = [
        {
            "fastmoss_shop_id": "1",
            "fastmoss_shop_name": "Eight Persent Store",
            "fastmoss_shop_url": "https://www.fastmoss.com/shop-marketing/detail/1",
            "region_name": "Philippines",
            "category": "Menswear",
            "shop_logo": "https://example.test/logo.png",
            "currency": "PHP",
            "total_sales": 1000,
            "total_gmv": 50000,
            "product_count": 158,
            "last_data_date": "2026-07-27",
        }
    ]
    payload = search_fastmoss_shops("Eight Persent", limit=10)
    assert payload["results"][0]["shopName"] == "Eight Persent Store"
    assert payload["results"][0]["shopId"] == "1"
    assert payload["results"][0]["matchLabel"] in {
        "Exact Match",
        "High Confidence",
    }


@patch("seller.intelligence.fastmoss_shop_search.fetch_recent_data")
@patch("seller.intelligence.fastmoss_shop_search.search_fastmoss_shops")
def test_get_fastmoss_shop_detail_computes_mtd_adg(mock_search, mock_recent):
    mock_search.return_value = {
        "results": [
            {
                "shopName": "Eight Persent Store",
                "shopId": "1",
                "shopUrl": "https://www.fastmoss.com/shop-marketing/detail/1",
                "region": "Philippines",
                "category": "Menswear",
                "shopLogo": "https://example.test/logo.png",
                "followers": None,
                "totalProducts": 158,
                "totalSales": 359359,
                "totalGmv": 44256852,
                "currency": "PHP",
                "lastDataDate": "2026-07-27",
            }
        ]
    }
    mock_recent.return_value = (
        {
            "total_info": {
                "shop_name": "Eight Persent Store",
                "region_name": "Philippines",
                "currency": "PHP",
                "sold_count": 5339,
                "sale_amount": 545335.27,
                "sold_product_count": 63,
                "author_count": 377,
                "live_count": 57,
                "aweme_count": 444,
            }
        },
        "https://example.test/recentData",
        None,
    )
    detail = get_fastmoss_shop_detail(shop_id="1", shop_name="Eight Persent Store", force_refresh=True)
    assert detail["mtdPeriod"] == {"startDate": "2026-07-01", "endDate": "2026-07-27"}
    assert detail["elapsedDays"] == 27
    assert detail["mtdSales"] == 545335.27
    assert detail["mtdOrders"] == 5339
    assert round(detail["mtdAdg"], 4) == round(545335.27 / 27, 4)
    assert detail["activeProducts"] == 63


@patch("seller.intelligence.fastmoss_shop_search.fetch_recent_data")
@patch("seller.intelligence.fastmoss_shop_search.search_fastmoss_shops")
def test_get_fastmoss_shop_detail_handles_missing_mtd_sales(mock_search, mock_recent):
    mock_search.return_value = {
        "results": [
            {"shopName": "Demo", "shopId": "1", "lastDataDate": "2026-07-27", "currency": "PHP"}
        ]
    }
    mock_recent.return_value = ({"total_info": {"sold_count": 10}}, "https://example.test", None)
    detail = get_fastmoss_shop_detail(shop_id="1", shop_name="Demo", force_refresh=True)
    assert detail["mtdSales"] is None
    assert detail["mtdAdg"] is None
