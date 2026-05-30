"""
Metric calculation logic — separate from UI and recommendations.
"""

from __future__ import annotations

from typing import Any


def _safe_num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def calculate_growth(mtd: Any, m1: Any) -> float | None:
    """Growth % from M-1 to MTD. Returns None if not calculable."""
    mtd_v = _safe_num(mtd)
    m1_v = _safe_num(m1)
    if mtd_v is None or m1_v is None:
        return None
    if m1_v == 0:
        return None
    return round(((mtd_v - m1_v) / abs(m1_v)) * 100, 2)


def format_value(value: Any, metric_key: str) -> str:
    v = _safe_num(value)
    if v is None:
        return "N/A"
    pct_metrics = (
        "cr",
        "adg_pct",
        "take_rate",
        "comm_rate",
        "adopted_gmv_pct",
        "gmv_adoption_pct",
        "ado_contribution_ls",
        "adg_pct_seller_kol",
        "fbs_ado_pct",
        "bid_rate",
        "item_order",
    )
    if metric_key in pct_metrics or metric_key.endswith("_pct") or "%" in metric_key:
        return f"{v:.2f}%"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"{v / 1_000:.1f}K"
    if v == int(v):
        return str(int(v))
    return f"{v:.2f}"


def get_metric_status(metric_name: str, value: Any, growth: float | None) -> dict[str, str]:
    """
    Status badge + suggested action per metric.
    Returns status: good | warning | critical | neutral
    """
    name = metric_name.lower()
    g = growth
    v = _safe_num(value)

    if v is None and g is None:
        return {"status": "neutral", "suggested_action": "Monitor — data unavailable"}

    # Declining core commercial
    if name in ("adgmv", "ado", "uv") and g is not None and g < -8:
        return {
            "status": "critical",
            "suggested_action": "Review traffic, pricing, and campaign mix urgently",
        }

    # Conversion down while traffic up
    if name == "cr" and g is not None and g < -5:
        return {
            "status": "warning",
            "suggested_action": "Improve PDP quality, pricing, and MDV coverage",
        }

    # ROAS thresholds
    if "roas" in name:
        if v is not None and v >= 8 and g is not None and g >= 0:
            return {"status": "good", "suggested_action": "Scale budget while monitoring take rate"}
        if v is not None and v < 5:
            return {
                "status": "warning",
                "suggested_action": "Review keywords, creatives, and hero SKU selection",
            }

    if "take_rate" in name and v is not None and v < 2.0 and g is not None and g < 0:
        return {
            "status": "warning",
            "suggested_action": "Increase ad spend if ROAS supports it",
        }

    if "gmv_adoption" in name or name == "gmv_adoption_pct":
        if v is not None and v < 30:
            return {
                "status": "warning",
                "suggested_action": "Increase MDV coverage on hero SKUs",
            }

    if "bid_rate" in name and v is not None and v < 25:
        return {
            "status": "warning",
            "suggested_action": "Nominate more eligible SKUs for price bidding",
        }

    if "fbs_ado_pct" in name and v is not None and v < 12:
        return {
            "status": "warning",
            "suggested_action": "Push best-selling SKUs into FBS",
        }

    if "ado_contribution" in name and v is not None and v < 5:
        return {
            "status": "warning",
            "suggested_action": "Test livestream campaigns and increase LS hours",
        }

    if "adg_pct_seller" in name or name == "adg_pct_seller_kol":
        if g is not None and g > 15:
            return {
                "status": "good",
                "suggested_action": "Increase KOL investment and video boosting",
            }

    if g is not None and g >= 5:
        return {"status": "good", "suggested_action": "Maintain momentum; document winning tactics"}
    if g is not None and g <= -5:
        return {"status": "warning", "suggested_action": "Investigate root cause and run recovery plan"}

    return {"status": "neutral", "suggested_action": "Continue monitoring week over week"}


def build_metric_row(metric_key: str, label: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Legacy helper; prefer metric_resolver output."""
    mtd = raw.get("mtd")
    m1 = raw.get("m1")
    growth = calculate_growth(mtd, m1)
    status_info = get_metric_status(metric_key, mtd, growth)
    return {
        "key": metric_key,
        "label": label,
        "mtdValue": mtd,
        "m1Value": m1,
        "calculatedValue": mtd,
        "mtd": mtd,
        "m1": m1,
        "mtd_display": format_value(mtd, metric_key),
        "m1_display": format_value(m1, metric_key),
        "growthPct": growth,
        "growth": growth,
        "growth_display": f"{growth:+.2f}%" if growth is not None else "N/A",
        "valueType": "Direct",
        "sourceFieldsUsed": [],
        "calculationFormula": "Legacy mock row",
        "healthStatus": status_info["status"],
        "suggested_action": status_info["suggested_action"],
        "missingFields": [],
    }


SECTION_CONFIG: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "commercial",
        "Commercial Overview",
        [
            ("adgmv", "ADGMV"),
            ("ado", "ADO"),
            ("abs", "ABS"),
            ("asp", "ASP"),
            ("item_order", "Item/Order"),
            ("uv", "UV"),
            ("cr", "CR"),
        ],
    ),
    (
        "paid_ads",
        "Paid Ads",
        [
            ("adg_pct", "Adg%"),
            ("take_rate", "Take Rate"),
            ("roas", "ROAS"),
        ],
    ),
    (
        "mpa_cpas",
        "MPA + CPAS",
        [
            ("adg_pct", "Adg%"),
            ("adopted_gmv_pct", "Adopted GMV%"),
            ("take_rate", "Take Rate"),
            ("roas", "ROAS"),
        ],
    ),
    (
        "ams",
        "AMS",
        [
            ("ams_adgmv", "AMS Adgmv"),
            ("take_rate", "Take Rate"),
            ("comm_rate", "Comm Rate"),
            ("roas", "ROAS"),
        ],
    ),
    (
        "livestream",
        "Livestream",
        [
            ("seller_ls_adg_pct", "Seller LS Adg%"),
            ("seller_ls_hrs", "Seller LS Hrs"),
            ("ado_contribution_ls", "ADO Contribution of LS"),
        ],
    ),
    (
        "video",
        "Video",
        [("adg_pct_seller_kol", "Adg% (Seller + KOL)")],
    ),
    (
        "mdv",
        "MDV",
        [("adg_pct", "Adg%"), ("gmv_adoption_pct", "GMV Adoption %")],
    ),
    (
        "atc",
        "ATC Participation",
        [
            ("dday", "DDay"),
            ("payday_15", "Payday-15"),
            ("payday_30", "Payday-30"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("sku_count", "SKU Count"),
        ],
    ),
    (
        "price_bidding",
        "Price Bidding",
        [
            ("eligible_sku", "Eligible SKU"),
            ("bidded_sku", "Bidded SKU"),
            ("bid_rate", "Bid Rate"),
        ],
    ),
    (
        "fbs",
        "FBS",
        [("fbs_ado", "FBS ADO"), ("fbs_ado_pct", "FBS ADO%")],
    ),
]


def build_sections_from_raw_row(raw_row: dict[str, Any]) -> list[dict[str, Any]]:
    from seller.metric_resolver import resolve_sections_from_raw

    return resolve_sections_from_raw(raw_row)


def build_sections(shop: dict[str, Any]) -> list[dict[str, Any]]:
    raw = shop.get("raw")
    if isinstance(raw, dict) and raw:
        return build_sections_from_raw_row(raw)
    sections = []
    for section_key, title, metrics in SECTION_CONFIG:
        section_data = shop.get(section_key, {}) or {}
        rows = []
        for metric_key, label in metrics:
            block = section_data.get(metric_key, {})
            if not isinstance(block, dict):
                block = {"mtd": block, "m1": None}
            rows.append(build_metric_row(metric_key, label, block))
        sections.append({"key": section_key, "title": title, "metrics": rows})
    return sections


def _metric_mtd(index: dict[str, dict[str, Any]], section: str, key: str) -> Any:
    m = index.get(section, {}).get(key, {})
    return m.get("mtdValue", m.get("mtd"))


def _metric_m1(index: dict[str, dict[str, Any]], section: str, key: str) -> Any:
    m = index.get(section, {}).get(key, {})
    return m.get("m1Value", m.get("m1"))


def calculate_health_score_from_sections(sections: list[dict[str, Any]]) -> dict[str, Any]:
    """0–100 health score from resolved dashboard sections."""
    from seller.metric_resolver import metric_lookup

    idx = metric_lookup(sections)
    score = 70
    flags: list[str] = []

    adgmv_g = calculate_growth(_metric_mtd(idx, "commercial", "adgmv"), _metric_m1(idx, "commercial", "adgmv"))
    ado_g = calculate_growth(_metric_mtd(idx, "commercial", "ado"), _metric_m1(idx, "commercial", "ado"))
    uv_g = calculate_growth(_metric_mtd(idx, "commercial", "uv"), _metric_m1(idx, "commercial", "uv"))
    cr_g = calculate_growth(_metric_mtd(idx, "commercial", "cr"), _metric_m1(idx, "commercial", "cr"))

    for label, g in (("ADGMV", adgmv_g), ("ADO", ado_g), ("UV", uv_g)):
        if g is not None:
            if g >= 5:
                score += 4
            elif g <= -8:
                score -= 12
                flags.append(f"{label} declining ({g:+.1f}%)")

    if uv_g is not None and uv_g > 5 and cr_g is not None and cr_g < -3:
        score -= 8
        flags.append("UV up but CR down")

    if adgmv_g is not None and ado_g is not None and uv_g is not None:
        if adgmv_g < -8 and ado_g < -8 and uv_g < -8:
            score -= 20
            flags.append("High risk: ADGMV, ADO, UV all declining")

    roas = _safe_num(_metric_mtd(idx, "paid_ads", "roas"))
    if roas is not None and roas >= 8:
        score += 5
    elif roas is not None and roas < 4:
        score -= 6

    mdv_adopt = _safe_num(_metric_mtd(idx, "mdv", "gmv_adoption_pct"))
    if mdv_adopt is not None and mdv_adopt < 25:
        score -= 5

    score = max(0, min(100, score))
    if score >= 75:
        label = "Healthy"
    elif score >= 50:
        label = "Needs Attention"
    else:
        label = "At Risk"

    return {"score": score, "label": label, "flags": flags}


def calculate_health_score(shop: dict[str, Any]) -> dict[str, Any]:
    if isinstance(shop.get("raw"), dict):
        sections = build_sections_from_raw_row(shop["raw"])
        return calculate_health_score_from_sections(sections)
    if isinstance(shop, list):
        return calculate_health_score_from_sections(shop)
    sections = build_sections(shop)
    return calculate_health_score_from_sections(sections)


# Aliases for required API names
calculateGrowth = calculate_growth
getMetricStatus = get_metric_status
calculateHealthScore = calculate_health_score
