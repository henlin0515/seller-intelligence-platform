"""
Seller Dashboard API service layer.
Loads full raw row from mirror sheet cache, then resolves metrics.
"""

from __future__ import annotations

from typing import Any

from seller.dashboard_visibility import apply_dashboard_visibility
from seller.insights import build_insights
from seller.metric_resolver import build_dashboard_from_raw, metric_lookup, shop_info_from_raw
from seller.metrics import calculate_health_score_from_sections
from seller.raw_data import SHEET_NAME, get_raw_shop_row, search_raw_shops
from seller.recommendations import generate_recommendations
from seller.sheets_cache import get_status


def build_chart_data(sections: list[dict[str, Any]]) -> dict[str, Any]:
    idx = metric_lookup(sections)
    commercial = idx.get("commercial", {})
    paid = idx.get("paid_ads", {})
    mpa = idx.get("mpa", {})
    ams = idx.get("ams", {})
    video = idx.get("video", {})
    mdv = idx.get("mdv", {})
    fbs = idx.get("fbs", {})

    def pair(section: dict[str, dict[str, Any]], metric: str) -> dict[str, Any]:
        block = section.get(metric, {})
        return {
            "mtd": block.get("mtdValue", block.get("mtd")),
            "m1": block.get("m1Value", block.get("m1")),
        }

    tools: list[dict[str, Any]] = []
    if paid.get("roas", {}).get("mtdValue") is not None:
        tools.append(
            {
                "tool": "Paid Ads",
                "roas_mtd": paid.get("roas", {}).get("mtdValue"),
                "adg_mtd": paid.get("adg_pct", {}).get("mtdValue"),
            }
        )
    if video.get("adg_pct", {}).get("mtdValue") is not None:
        tools.append(
            {
                "tool": "Video",
                "roas_mtd": None,
                "adg_mtd": video.get("adg_pct", {}).get("mtdValue"),
            }
        )
    if mdv.get("adg_pct", {}).get("mtdValue") is not None:
        tools.append(
            {
                "tool": "MDV",
                "roas_mtd": None,
                "adg_mtd": mdv.get("adg_pct", {}).get("mtdValue"),
            }
        )
    if ams.get("take_rate", {}).get("mtdValue") is not None:
        tools.append(
            {
                "tool": "AMS",
                "roas_mtd": None,
                "adg_mtd": ams.get("take_rate", {}).get("mtdValue"),
            }
        )
    if mpa.get("take_rate", {}).get("mtdValue") is not None:
        tools.append(
            {
                "tool": "MPA",
                "roas_mtd": None,
                "adg_mtd": mpa.get("take_rate", {}).get("mtdValue"),
            }
        )
    if fbs.get("fbs_gmv", {}).get("mtdValue") is not None:
        tools.append(
            {
                "tool": "FBS",
                "roas_mtd": None,
                "adg_mtd": fbs.get("fbs_gmv", {}).get("mtdValue"),
            }
        )

    return {
        "adgmv_ado": {
            "adgmv": pair(commercial, "adgmv"),
            "ado": pair(commercial, "ado"),
        },
        "traffic_conversion": {
            "uv": pair(commercial, "uv"),
        },
        "tool_performance": tools,
    }


def get_dashboard_payload(shop_id: str) -> dict[str, Any] | None:
    entry = get_raw_shop_row(shop_id)
    if not entry:
        return None

    raw = entry["raw"]
    resolved = build_dashboard_from_raw(raw)
    # Full resolved index for recommendations (uses raw row + all mapped logic).
    full_index = resolved["metricIndex"]
    sections = apply_dashboard_visibility(resolved["sections"])
    health = calculate_health_score_from_sections(sections)
    shop_meta = shop_info_from_raw(raw, entry["shop_id"], entry.get("shop_name", ""))

    recommendations = generate_recommendations(
        sections=sections,
        raw_data=raw,
        metric_index=full_index,
    )

    return {
        "shop": {
            "shop_id": shop_meta["shop_id"],
            "shop_name": shop_meta["shop_name"],
            "tier": shop_meta.get("tier") or entry.get("tier") or "",
            "category": shop_meta.get("category") or entry.get("category") or "",
            "bu": shop_meta.get("bu") or "",
            "lead": shop_meta.get("lead") or "",
        },
        "sections": sections,
        "health": health,
        "insights": build_insights(sections, health),
        "recommendations": _sanitize_recommendations(recommendations),
        "charts": build_chart_data(sections),
    }


def _sanitize_recommendations(recs: list[dict[str, str]]) -> list[dict[str, str]]:
    """Business-facing recommendation cards only."""
    return [
        {
            "priority": r.get("priority", "Low"),
            "issue_found": r.get("issue_found", ""),
            "recommended_action": r.get("recommended_action", ""),
            "supporting_data": r.get("supporting_data", ""),
            "expected_impact": r.get("expected_impact", ""),
        }
        for r in recs
    ]


def search_seller_shops(query: str) -> list[dict[str, str]]:
    return search_raw_shops(query)


def get_seller_data_status() -> dict[str, Any]:
    return get_status()
