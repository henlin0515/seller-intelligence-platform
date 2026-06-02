"""Tests for portfolio Business Intelligence aggregates."""

from seller.intelligence.business.portfolio import build_portfolio_overview


def _seller(
    *,
    shop_id: str,
    name: str,
    mapped: bool = True,
    sh_mtd=100.0,
    sh_m1=80.0,
    tk_mtd=50.0,
    tk_m1=40.0,
):
    row = {
        "shop_id": shop_id,
        "shop_name": name,
        "fastmoss_match_status": "MAPPED" if mapped else "NOT_FOUND",
        "fastmoss_review_status": "APPROVED" if mapped else "PENDING_REVIEW",
        "shopee_mtd_adgmv_usd": sh_mtd,
        "shopee_m1_adgmv_usd": sh_m1,
        "tiktok_mtd_adgmv_usd": tk_mtd,
        "tiktok_m1_adgmv_usd": tk_m1,
        "mtd_shopee_sob_percent": None,
        "mtd_tiktok_sob_percent": None,
        "tiktok_mom_percent": None,
    }
    total = sh_mtd + tk_mtd
    if total:
        row["mtd_shopee_sob_percent"] = round(sh_mtd / total * 100, 1)
        row["mtd_tiktok_sob_percent"] = round(tk_mtd / total * 100, 1)
    return row


def test_portfolio_totals_and_sob():
    sellers = [
        _seller(shop_id="1", name="Alpha", sh_mtd=100, sh_m1=80, tk_mtd=100, tk_m1=80),
        _seller(shop_id="2", name="Beta", sh_mtd=50, sh_m1=50, tk_mtd=50, tk_m1=50),
        _seller(shop_id="3", name="Gamma", mapped=False, sh_mtd=999, tk_mtd=999),
    ]
    p = build_portfolio_overview(sellers, total_sellers=3)

    assert p["total_sellers"] == 3
    assert p["mapped_sellers"] == 2
    assert p["shopee_mtd_adgmv_usd"] == 150.0
    assert p["tiktok_mtd_adgmv_usd"] == 150.0
    assert p["portfolio_total_mtd_adgmv_usd"] == 300.0
    assert p["portfolio_sob_mtd_shopee_percent"] == 50.0
    assert p["portfolio_sob_mtd_tiktok_percent"] == 50.0
    assert p["mapping_rate_percent"] == 66.7


def test_portfolio_segmentation_and_top_lists():
    sellers = [
        _seller(shop_id="1", name="Grow", sh_mtd=120, sh_m1=50, tk_mtd=30, tk_m1=20),
        _seller(shop_id="2", name="Flat", sh_mtd=100, sh_m1=100, tk_mtd=0, tk_m1=0),
        _seller(shop_id="3", name="Down", sh_mtd=40, sh_m1=100, tk_mtd=10, tk_m1=50),
    ]
    p = build_portfolio_overview(sellers, total_sellers=3)

    assert p["growing_seller_count"] == 1
    assert p["flat_seller_count"] == 1
    assert p["declining_seller_count"] == 1
    assert len(p["top5_seller_contribution"]) == 3
    assert p["top5_seller_contribution"][0]["shop_name"] == "Grow"
    assert p["top_tiktok_threat_sellers"][0]["shop_name"] == "Grow"
