"""Tests for TikTok Product Radar scoring."""

from __future__ import annotations

from datetime import date, timedelta

from seller.intelligence.assortment.radar import (
    NEW_PRODUCT_DAYS,
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
