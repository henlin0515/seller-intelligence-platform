"""Tests for TikTok Product Radar scoring."""

from __future__ import annotations

from datetime import date, timedelta

from seller.intelligence.assortment.radar import (
    NEW_PRODUCT_DAYS,
    _build_category_dashboard,
    _build_shop_view,
    compute_growth_raw,
    days_since_launch,
    enrich_product_metrics,
    new_product_badge,
)


def test_new_product_badge_buckets():
    assert new_product_badge(2) == "3 DAYS"
    assert new_product_badge(5) == "7 DAYS"
    assert new_product_badge(10) == "14 DAYS"
    assert new_product_badge(18) == "20 DAYS"
    assert new_product_badge(30) is None


def test_days_since_launch():
    today = date(2026, 6, 1)
    upload = (today - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    assert days_since_launch(upload, today=today) == 5


def test_enrich_product_metrics_assigns_opportunity():
    today = date(2026, 6, 1)
    recent = (today - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    old = (today - timedelta(days=400)).strftime("%Y-%m-%d %H:%M:%S")
    products = [
        {
            "product_id": "1",
            "product_name": "Alpha",
            "sales_amount": 1000,
            "sold_count": 10,
            "upload_date": recent,
            "relate_video_count": 50,
        },
        {
            "product_id": "2",
            "product_name": "Beta",
            "sales_amount": 500000,
            "sold_count": 5000,
            "upload_date": old,
            "relate_video_count": 5000,
            "relate_live_count": 2000,
        },
    ]
    enriched = enrich_product_metrics(products, today=today)
    assert len(enriched) == 2
    assert enriched[0]["is_new_product"] is True
    assert enriched[0]["days_since_launch"] <= NEW_PRODUCT_DAYS
    assert enriched[1]["growth_score"] >= enriched[0]["growth_score"]
    assert all("opportunity_score" in row for row in enriched)


def test_compute_growth_raw_uses_inc_fields():
    base = compute_growth_raw({"sales_amount": 100, "sold_count": 1, "days_since_launch": 10})
    boosted = compute_growth_raw(
        {
            "sales_amount": 100,
            "sold_count": 1,
            "days_since_launch": 10,
            "inc_sold_count": 100,
            "inc_sale_amount": 5000,
        }
    )
    assert boosted > base


def test_build_shop_view_groups_by_shop():
    today = date(2026, 6, 1)
    recent = (today - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")
    products = enrich_product_metrics(
        [
            {
                "product_id": "a1",
                "product_name": "Alpha Tee",
                "category": "Fashion",
                "sales_amount": 1000,
                "sold_count": 10,
                "upload_date": recent,
                "seller_shop_id": "1",
                "seller_shop_name": "Shop A",
            },
            {
                "product_id": "b1",
                "product_name": "Beta Bag",
                "category": "Bags",
                "sales_amount": 5000,
                "sold_count": 50,
                "upload_date": recent,
                "seller_shop_id": "2",
                "seller_shop_name": "Shop B",
            },
        ],
        today=today,
    )
    payload = _build_shop_view(products)
    assert len(payload["shops"]) == 2
    shop_a = next(s for s in payload["shops"] if s["shop_id"] == "1")
    assert shop_a["summary"]["total_products"] == 1
    assert shop_a["top_products"][0]["rank"] == 1
    assert shop_a["new_products"][0]["product_id"] == "a1"


def test_build_category_dashboard_groups_and_summaries():
    today = date(2026, 6, 1)
    recent = (today - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    old = (today - timedelta(days=120)).strftime("%Y-%m-%d %H:%M:%S")
    products = enrich_product_metrics(
        [
            {
                "product_id": "f1",
                "product_name": "Fresh Item",
                "category": "Beauty",
                "sales_amount": 900,
                "sold_count": 9,
                "upload_date": recent,
                "seller_shop_id": "10",
                "seller_shop_name": "Glow Shop",
            },
            {
                "product_id": "f2",
                "product_name": "Classic Item",
                "category": "Beauty",
                "sales_amount": 300,
                "sold_count": 3,
                "upload_date": old,
                "seller_shop_id": "11",
                "seller_shop_name": "Other Shop",
            },
        ],
        today=today,
    )
    payload = _build_category_dashboard(products)
    assert len(payload["categories"]) == 1
    summary = payload["categories"][0]
    assert summary["category"] == "Beauty"
    assert summary["total_products"] == 2
    assert summary["new_products_20d"] == 1
    assert summary["top_shop"]["shop_name"] == "Glow Shop"
    detail = payload["category_details"]["Beauty"]
    assert detail["top_products"][0]["product_name"] == "Fresh Item"
    assert detail["new_products"][0]["days_since_launch"] == 2
    assert detail["top_shops"][0]["shop_name"] == "Glow Shop"
