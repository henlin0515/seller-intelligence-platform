"""
Executive dashboard layout — fixed sections for every seller.

Always returns the same section list and metric rows. Missing mapped data → N/A.
Internal resolver fields are stripped from API responses.
"""

from __future__ import annotations

from typing import Any

# Resolver-only sections (not on business dashboard).
_EXCLUDE_RESOLVER_KEYS: frozenset[str] = frozenset(
    {"atc", "price_bidding", "organic_traffic"}
)

SECTION_DISPLAY_TITLES: dict[str, str] = {
    "shop_info": "Shop Info",
    "commercial": "Commercial Overview",
    "paid_ads": "Paid Ads",
    "ams": "AMS",
    "mpa": "MPA",
    "fbs": "FBS",
    "livestream": "Livestream",
    "video": "Video",
    "mdv": "MDV",
}

# Fixed metric order per section (resolver keys).
SECTION_METRIC_ORDER: dict[str, tuple[str, ...]] = {
    "shop_info": (
        "shop_id",
        "shop_name",
        "managed_tier",
        "bu",
        "lead",
        "bd_category",
    ),
    "commercial": ("adgmv", "ado", "uv", "item_order"),
    "paid_ads": (
        "ads_spend",
        "ads_gmv",
        "ads_adopted",
        "roas",
        "take_rate",
        "adg_pct",
    ),
    "ams": ("ams_spend", "take_rate"),
    "mpa": ("mpa_gmv", "take_rate"),
    "fbs": ("fbs_gmv", "fbs_ado"),
    "livestream": ("seller_ls_hrs",),
    "video": ("video_adgmv", "adg_pct", "new_uploads"),
    "mdv": ("mdv_adgmv", "adg_pct"),
}

SECTION_ORDER: tuple[str, ...] = (
    "shop_info",
    "commercial",
    "paid_ads",
    "ams",
    "mpa",
    "fbs",
    "livestream",
    "video",
    "mdv",
)

BUSINESS_LABELS: dict[tuple[str, str], str] = {
    ("shop_info", "shop_id"): "Shop ID",
    ("shop_info", "shop_name"): "Shop Name",
    ("shop_info", "managed_tier"): "Managed Tier",
    ("shop_info", "bu"): "BU",
    ("shop_info", "lead"): "Lead",
    ("shop_info", "bd_category"): "BD Category",
    ("commercial", "adgmv"): "ADGMV",
    ("commercial", "ado"): "ADO",
    ("commercial", "uv"): "UV",
    ("commercial", "item_order"): "Orders",
    ("paid_ads", "ads_spend"): "Ads Spend",
    ("paid_ads", "ads_gmv"): "Ads GMV",
    ("paid_ads", "ads_adopted"): "Ads Adopted",
    ("paid_ads", "roas"): "ROAS",
    ("paid_ads", "take_rate"): "Take Rate",
    ("paid_ads", "adg_pct"): "Adg%",
    ("ams", "ams_spend"): "AMS Spend",
    ("ams", "take_rate"): "AMS Take Rate",
    ("mpa", "mpa_gmv"): "MPA GMV",
    ("mpa", "take_rate"): "MPA Take Rate",
    ("fbs", "fbs_gmv"): "FBS GMV",
    ("fbs", "fbs_ado"): "FBS ADO",
    ("livestream", "seller_ls_hrs"): "Seller LS Hours",
    ("video", "video_adgmv"): "Video ADGMV",
    ("video", "adg_pct"): "Video Adg%",
    ("video", "new_uploads"): "New Uploads",
    ("mdv", "mdv_adgmv"): "MDV ADGMV",
    ("mdv", "adg_pct"): "MDV Adg%",
}

# UI shows M-1 and growth as em dash for these metrics.
MTD_ONLY_METRICS: frozenset[tuple[str, str]] = frozenset(
    {
        ("ams", "take_rate"),
        ("video", "adg_pct"),
        ("mdv", "adg_pct"),
    }
)

_UI_STRIP_KEYS: frozenset[str] = frozenset(
    {
        "sourceFieldsUsed",
        "calculationFormula",
        "missingFields",
        "valueType",
        "calculatedValue",
        "suggested_action",
    }
)


def _has_value(metric: dict[str, Any]) -> bool:
    if metric.get("valueType") == "N/A":
        return False
    if metric.get("mtdValue") is not None or metric.get("m1Value") is not None:
        return True
    mtd_d = str(metric.get("mtd_display") or "").strip()
    m1_d = str(metric.get("m1_display") or "").strip()
    return (mtd_d and mtd_d not in ("N/A", "—")) or (m1_d and m1_d not in ("N/A", "—"))


def _placeholder_metric(section_key: str, metric_key: str) -> dict[str, Any]:
    label = BUSINESS_LABELS.get((section_key, metric_key), metric_key)
    return {
        "key": metric_key,
        "label": label,
        "mtdValue": None,
        "m1Value": None,
        "mtd": None,
        "m1": None,
        "mtd_display": "N/A",
        "m1_display": "N/A",
        "growthPct": None,
        "growth": None,
        "growth_display": "N/A",
        "healthStatus": "neutral",
    }


def _sanitize_metric(section_key: str, metric: dict[str, Any]) -> dict[str, Any]:
    key = metric.get("key", "")
    out: dict[str, Any] = {k: v for k, v in metric.items() if k not in _UI_STRIP_KEYS}
    label = BUSINESS_LABELS.get((section_key, key))
    if label:
        out["label"] = label
    if not _has_value(metric):
        out["mtd_display"] = out.get("mtd_display") or "N/A"
        out["m1_display"] = out.get("m1_display") or "N/A"
        out["growth_display"] = out.get("growth_display") or "N/A"
    if (section_key, key) in MTD_ONLY_METRICS:
        out["m1_display"] = "—"
        out["m1Value"] = None
        out["m1"] = None
        out["growth_display"] = "—"
        out["growthPct"] = None
        out["growth"] = None
    return out


def _build_section(section_key: str, resolved_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    by_key = {m.get("key"): m for m in resolved_metrics if m.get("key")}
    metrics: list[dict[str, Any]] = []
    for metric_key in SECTION_METRIC_ORDER.get(section_key, ()):
        raw = by_key.get(metric_key)
        if raw and _has_value(raw):
            metrics.append(_sanitize_metric(section_key, raw))
        else:
            metrics.append(_placeholder_metric(section_key, metric_key))
    return {
        "key": section_key,
        "title": SECTION_DISPLAY_TITLES[section_key],
        "metrics": metrics,
    }


def apply_dashboard_visibility(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Always return the full executive dashboard structure for every seller."""
    by_key = {s["key"]: s for s in sections if s["key"] not in _EXCLUDE_RESOLVER_KEYS}
    out: list[dict[str, Any]] = []
    for section_key in SECTION_ORDER:
        src = by_key.get(section_key)
        resolved = src.get("metrics", []) if src else []
        out.append(_build_section(section_key, resolved))
    return out
