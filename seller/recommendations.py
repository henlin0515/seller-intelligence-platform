"""
AI-style business recommendations from resolved dashboard metrics + raw row.
Uses displayed metrics only (no processed tabs).
"""

from __future__ import annotations

from typing import Any

from seller.metrics import _safe_num, calculate_growth, format_value


def _m(index: dict[str, dict[str, dict[str, Any]]], section: str, key: str) -> dict[str, Any]:
    return index.get(section, {}).get(key, {})


def _mtd(index: dict[str, dict[str, dict[str, Any]]], section: str, key: str) -> float | None:
    block = _m(index, section, key)
    return _safe_num(block.get("mtdValue", block.get("mtd")))


def _growth(index: dict[str, dict[str, dict[str, Any]]], section: str, key: str) -> float | None:
    block = _m(index, section, key)
    return calculate_growth(
        block.get("mtdValue", block.get("mtd")),
        block.get("m1Value", block.get("m1")),
    )


def _fmt_metric(index: dict[str, dict[str, dict[str, Any]]], section: str, key: str) -> str:
    block = _m(index, section, key)
    return format_value(block.get("mtdValue"), key)


def generate_recommendations(
    *,
    sections: list[dict[str, Any]] | None = None,
    raw_data: dict[str, Any] | None = None,
    metric_index: dict[str, dict[str, dict[str, Any]]] | None = None,
    shop: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """
    Accepts resolved sections + raw_data (preferred) or legacy nested shop dict.
    """
    from seller.metric_resolver import build_dashboard_from_raw, metric_lookup

    idx = metric_index
    if idx is None and sections is not None:
        idx = metric_lookup(sections)
    elif idx is None and shop is not None:
        raw = shop.get("raw")
        if isinstance(raw, dict):
            resolved = build_dashboard_from_raw(raw)
            idx = resolved["metricIndex"]
        else:
            idx = _legacy_index(shop)

    if not idx:
        return [
            {
                "priority": "Low",
                "issue_found": "Insufficient data for recommendations",
                "supporting_data": "Raw row or resolved metrics unavailable",
                "recommended_action": "Verify [Raw] Shop Level - Fashion row loads correctly",
                "expected_impact": "Actionable insights once data is available",
            }
        ]

    recs: list[dict[str, str]] = []

    uv_g = _growth(idx, "commercial", "uv")
    cr_g = _growth(idx, "commercial", "cr")
    if uv_g is not None and cr_g is not None and uv_g > 3 and cr_g < -3:
        recs.append(
            {
                "priority": "High",
                "issue_found": "Traffic is growing but conversion rate is declining",
                "supporting_data": (
                    f"UV growth {uv_g:+.1f}% (MTD {_fmt_metric(idx, 'commercial', 'uv')}), "
                    f"CR growth {cr_g:+.1f}% (MTD {_fmt_metric(idx, 'commercial', 'cr')})"
                ),
                "recommended_action": "Improve pricing, PDP quality, MDV coverage, and assortment quality",
                "expected_impact": "Higher CR and ADO without losing traffic momentum",
            }
        )

    roas = _mtd(idx, "paid_ads", "roas")
    take = _mtd(idx, "paid_ads", "take_rate")
    if roas is not None and take is not None and roas >= 8 and take < 2.0:
        recs.append(
            {
                "priority": "High",
                "issue_found": "Paid Ads ROAS is strong but take rate is low",
                "supporting_data": (
                    f"Paid Ads ROAS is {roas:.1f}x, but Take Rate is only {take:.2f}%, "
                    "so the shop may have room to scale ads investment."
                ),
                "recommended_action": "Increase ads budget on top-performing campaigns",
                "expected_impact": "Incremental ADGMV with efficient returns",
            }
        )
    if roas is not None and roas < 5:
        recs.append(
            {
                "priority": "High",
                "issue_found": "Paid Ads ROAS is below target",
                "supporting_data": f"Paid Ads ROAS MTD {roas:.1f}x (from resolved dashboard metrics)",
                "recommended_action": "Review keyword targeting, creatives, and hero SKU selection",
                "expected_impact": "Improved ROAS and lower wasted ad spend",
            }
        )

    mdv_adopt = _mtd(idx, "mdv", "gmv_adoption_pct")
    if mdv_adopt is not None and mdv_adopt < 35:
        recs.append(
            {
                "priority": "Medium",
                "issue_found": "MDV GMV Adoption % is low",
                "supporting_data": f"GMV Adoption % MTD {mdv_adopt:.1f}%",
                "recommended_action": "Increase MDV coverage on high-traffic SKUs",
                "expected_impact": "Higher voucher redemption and order uplift",
            }
        )

    ams_roas = _mtd(idx, "ams", "roas")
    ams_take = _mtd(idx, "ams", "take_rate")
    if ams_roas is not None and ams_roas >= 8:
        detail = f"AMS ROAS MTD {ams_roas:.1f}x"
        if ams_take is not None:
            detail += f", AMS Take Rate {ams_take:.2f}% of Total ADGMV"
        recs.append(
            {
                "priority": "Medium",
                "issue_found": "AMS ROAS is performing well",
                "supporting_data": detail,
                "recommended_action": "Increase affiliate commission or push more AMS creators",
                "expected_impact": "Expanded affiliate-driven GMV",
            }
        )

    video_g = _growth(idx, "video", "adg_pct")
    video_mtd = _mtd(idx, "video", "adg_pct")
    if video_g is not None and video_g > 10:
        recs.append(
            {
                "priority": "Medium",
                "issue_found": "Video Adg% (Seller + KOL) is growing",
                "supporting_data": (
                    f"Video Adg% MTD {video_mtd:.1f}% with growth {video_g:+.1f}% vs M-1"
                    if video_mtd is not None
                    else f"Video Adg% growth {video_g:+.1f}%"
                ),
                "recommended_action": "Increase KOL investment and video boosting",
                "expected_impact": "Stronger video-led traffic and conversion",
            }
        )

    ls_contrib = _mtd(idx, "livestream", "ado_contribution_ls")
    ls_hrs = _mtd(idx, "livestream", "seller_ls_hrs")
    if ls_contrib is not None and ls_contrib < 6:
        recs.append(
            {
                "priority": "Medium",
                "issue_found": "Livestream ADO contribution is low",
                "supporting_data": (
                    f"ADO Contribution of LS {ls_contrib:.1f}%"
                    + (f", Seller LS Hrs MTD {int(ls_hrs)}" if ls_hrs is not None else "")
                ),
                "recommended_action": "Test livestream campaigns and increase seller LS hours",
                "expected_impact": "Higher LS-driven orders and engagement",
            }
        )

    dday = _mtd(idx, "atc", "dday_submitted")
    payday15 = _mtd(idx, "atc", "payday15_submitted")
    if (dday or 0) < 1 and (payday15 or 0) < 1:
        recs.append(
            {
                "priority": "Medium",
                "issue_found": "ATC campaign participation is limited",
                "supporting_data": (
                    f"DDay participation {int(dday or 0)}, Payday-15 {int(payday15 or 0)} "
                    "(from raw ATC participation fields)"
                ),
                "recommended_action": "Join DDay and Payday ATC campaigns",
                "expected_impact": "Extra campaign traffic and promotional uplift",
            }
        )

    bid_rate = _mtd(idx, "price_bidding", "bid_rate")
    if bid_rate is not None and bid_rate < 25:
        eligible = _mtd(idx, "price_bidding", "eligible_sku")
        bidded = _mtd(idx, "price_bidding", "bidded_sku")
        recs.append(
            {
                "priority": "Low",
                "issue_found": "Price Bidding bid rate is low",
                "supporting_data": (
                    f"Bid Rate MTD {bid_rate:.1f}% "
                    f"({int(bidded or 0)} bidded / {int(eligible or 0)} eligible SKUs)"
                ),
                "recommended_action": "Nominate more eligible SKUs for price bidding",
                "expected_impact": "Better price competitiveness on search",
            }
        )

    fbs_pct = _mtd(idx, "fbs", "fbs_ado_pct")
    if fbs_pct is not None and fbs_pct < 12:
        recs.append(
            {
                "priority": "Low",
                "issue_found": "FBS ADO% is below benchmark",
                "supporting_data": f"FBS ADO% MTD {fbs_pct:.1f}% vs Total ADO",
                "recommended_action": "Push best-selling SKUs into FBS",
                "expected_impact": "Faster delivery perception and higher conversion",
            }
        )

    adgmv_g = _growth(idx, "commercial", "adgmv")
    ado_g = _growth(idx, "commercial", "ado")
    if (
        adgmv_g is not None
        and ado_g is not None
        and uv_g is not None
        and adgmv_g < -8
        and ado_g < -8
        and uv_g < -8
    ):
        recs.append(
            {
                "priority": "High",
                "issue_found": "Shop flagged as high risk — core metrics declining",
                "supporting_data": (
                    f"ADGMV {adgmv_g:+.1f}%, ADO {ado_g:+.1f}%, UV {uv_g:+.1f}% "
                    f"(Total ADGMV MTD {_fmt_metric(idx, 'commercial', 'adgmv')})"
                ),
                "recommended_action": "Run recovery workshop: assortment, pricing, ads, and platform tools",
                "expected_impact": "Stabilize GMV and traffic trend within 4–6 weeks",
            }
        )

    mpa_take = _mtd(idx, "mpa", "take_rate")
    mpa_gmv = _fmt_metric(idx, "mpa", "mpa_gmv")
    if mpa_take is not None and mpa_take >= 2:
        recs.append(
            {
                "priority": "Medium",
                "issue_found": "MPA take rate is active — review scale opportunity",
                "supporting_data": (
                    f"MPA Take Rate MTD {mpa_take:.2f}%"
                    + (f", MPA GMV {mpa_gmv}" if mpa_gmv != "N/A" else "")
                ),
                "recommended_action": "Scale MPA on hero SKUs while monitoring take rate vs ADGMV",
                "expected_impact": "Incremental MPA-attributed GMV",
            }
        )

    if not recs:
        adgmv = _fmt_metric(idx, "commercial", "adgmv")
        recs.append(
            {
                "priority": "Low",
                "issue_found": "No critical issues detected in current snapshot",
                "supporting_data": f"Core metrics within range (e.g. ADGMV MTD {adgmv})",
                "recommended_action": "Continue weekly monitoring and scale winning channels",
                "expected_impact": "Sustained growth across commercial and tools",
            }
        )

    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    recs.sort(key=lambda r: priority_order.get(r["priority"], 3))
    return recs


def _legacy_index(shop: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """Convert old nested shop dict to metric index shape."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for section_key, section_data in shop.items():
        if not isinstance(section_data, dict) or section_key in (
            "shop_id",
            "shop_name",
            "tier",
            "category",
            "raw",
        ):
            continue
        out[section_key] = {}
        for metric_key, block in section_data.items():
            if isinstance(block, dict):
                out[section_key][metric_key] = {
                    "mtdValue": block.get("mtd"),
                    "m1Value": block.get("m1"),
                }
    return out


generateRecommendations = generate_recommendations
