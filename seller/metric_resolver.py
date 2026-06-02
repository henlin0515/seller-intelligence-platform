"""
Resolve dashboard metrics from live AI DATA rawData fields.
Only mapped metrics are exposed to the dashboard UI.
"""

from __future__ import annotations

from typing import Any, Callable

from seller.ai_data_fields import (
    VIDEO_GMV_CONTRI_M1,
    VIDEO_GMV_CONTRI_MTD,
    resolve_raw_column,
)
from seller.metrics import calculate_growth, format_value, get_metric_status

MetricFn = Callable[[dict[str, Any]], list[dict[str, Any]]]

# Logical field keys (resolved to AI DATA headers via ai_data_fields.py)
K_ADGMV_MTD, K_ADGMV_M1 = "mtd_adg", "m1_adg"
K_ADO_MTD, K_ADO_M1 = "mtd_ado", "m1_ado"
K_UV_MTD, K_UV_M1 = "mtd_uv", "m1_uv"
K_ADS_EXP_MTD, K_ADS_EXP_M1 = "mtd_ads_exp", "m1_ads_exp"
K_ADS_GMV_MTD, K_ADS_GMV_M1 = "mtd_ads_adg", "m1_ads_adg"
K_ADS_ADOPT_MTD, K_ADS_ADOPT_M1 = "mtd_ads_adopted", "m1_ads_adopted"
K_MPA_GMV_MTD, K_MPA_GMV_M1 = "mtd_mpa_adg", "m1_mpa_adg"
K_MPA_EXP_MTD, K_MPA_EXP_M1 = "mtd_mpa_exp", "m1_mpa_exp"
K_MPA_ADOPT_MTD, K_MPA_ADOPT_M1 = "mtd_mpa_gmvcontri", "m1_mpa_gmvcontri"
K_AMS_GMV_MTD, K_AMS_GMV_M1 = "mtd_ams_adg", "m1_ams_adg"
K_AMS_EXP_MTD, K_AMS_EXP_M1 = "mtd_ams_exp", "m1_ams_exp"
K_AMS_ADOPT_MTD, K_AMS_ADOPT_M1 = "mtd_ams_adopted", "m1_ams_adopted"
K_LS_HRS_MTD, K_LS_HRS_M1 = "mtd_ls_hrs", "m1_ls_hrs"
K_LS_GMV_MTD, K_LS_GMV_M1 = "mtd_ls_adg", "m1_ls_adg"
K_VIDEO_GMV_MTD, K_VIDEO_GMV_M1 = "mtd_video_adg", "m1_video_adg"
K_NEW_UPLOADS_MTD, K_NEW_UPLOADS_M1 = "mtd_new_uploads", "m1_new_uploads"
K_MDV_GMV_MTD, K_MDV_GMV_M1 = "mtd_mdv_adg", "m1_mdv_adg"
K_MDV_ADOPT_MTD, K_MDV_ADOPT_M1 = "mtd_mdv_adgcov", "m1_mdv_adgcov"
K_FBS_GMV_MTD, K_FBS_GMV_M1 = "mtd_fbs_gmv", "m1_fbs_gmv"
K_FBS_ADO_MTD, K_FBS_ADO_M1 = "mtd_fbs_ado", "m1_fbs_ado"


def _value_present(value: Any) -> bool:
    if value is None:
        return False
    s = str(value).strip()
    if not s or s.lower() in ("#n/a", "n/a", "-", "", "#ref!", "#value!"):
        return False
    if s in ("$0.00", "$0", "0", "0.0", "0.00", "0.00%"):
        return True
    return True


def _num(value: Any) -> float | None:
    if not _value_present(value):
        return None
    try:
        s = str(value).strip().replace(",", "").replace("$", "")
        if s.endswith("%"):
            s = s[:-1].strip()
        if s in ("", "-", "#VALUE!", "#REF!"):
            return None
        v = float(s)
        return v
    except (TypeError, ValueError):
        return None


def _col(raw: dict[str, Any], logical_key: str) -> str | None:
    return resolve_raw_column(raw, logical_key)


def _raw(raw: dict[str, Any], logical_key: str) -> Any:
    col = _col(raw, logical_key)
    if col is None:
        return None
    return raw.get(col)


def _pair(
    raw: dict[str, Any], mtd_key: str, m1_key: str | None = None
) -> tuple[float | None, float | None, list[str]]:
    sources: list[str] = []
    mtd_col = _col(raw, mtd_key)
    mtd = _num(_raw(raw, mtd_key)) if mtd_col else None
    if mtd_col:
        sources.append(mtd_col)
    m1 = None
    if m1_key:
        m1_col = _col(raw, m1_key)
        if m1_col:
            sources.append(m1_col)
            m1 = _num(_raw(raw, m1_key))
    return mtd, m1, sources


def _div(n: float | None, d: float | None) -> float | None:
    if n is None or d is None or d == 0:
        return None
    return n / d


def _pct(part: float | None, whole: float | None) -> float | None:
    v = _div(part, whole)
    return round(v * 100, 2) if v is not None else None


def _make_metric(
    key: str,
    label: str,
    mtd: float | None,
    m1: float | None,
    *,
    value_type: str,
    source_fields: list[str],
    formula: str,
    missing_fields: list[str] | None = None,
) -> dict[str, Any]:
    growth = calculate_growth(mtd, m1)
    health = get_metric_status(key, mtd, growth)
    return {
        "key": key,
        "label": label,
        "mtdValue": mtd,
        "m1Value": m1,
        "calculatedValue": mtd,
        "mtd": mtd,
        "m1": m1,
        "mtd_display": format_value(mtd, key) if mtd is not None else "N/A",
        "m1_display": format_value(m1, key) if m1 is not None else "N/A",
        "growthPct": growth,
        "growth": growth,
        "growth_display": f"{growth:+.2f}%" if growth is not None else "N/A",
        "sourceFieldsUsed": source_fields,
        "calculationFormula": formula,
        "valueType": value_type,
        "healthStatus": health["status"],
        "suggested_action": health["suggested_action"],
        "missingFields": missing_fields or [],
    }


def _info(raw: dict[str, Any], key: str, label: str, logical_key: str) -> dict[str, Any]:
    col = _col(raw, logical_key)
    val = _raw(raw, logical_key) if col else None
    if not _value_present(val):
        return _na(key, label, [logical_key], f"Direct: {logical_key}")
    display = str(val).strip()
    m = _make_metric(
        key,
        label,
        _num(val),
        None,
        value_type="Direct",
        source_fields=[col] if col else [],
        formula=f"Direct: {logical_key} → {col}",
    )
    m["mtd_display"] = display
    m["m1_display"] = "—"
    m["growth_display"] = "—"
    m["growthPct"] = None
    m["growth"] = None
    return m


def _na(key: str, label: str, missing: list[str], formula: str) -> dict[str, Any]:
    return _make_metric(
        key,
        label,
        None,
        None,
        value_type="N/A",
        source_fields=[],
        formula=formula,
        missing_fields=missing,
    )


def _direct(
    raw: dict[str, Any],
    key: str,
    label: str,
    mtd_key: str,
    m1_key: str | None = None,
) -> dict[str, Any]:
    mtd, m1, sources = _pair(raw, mtd_key, m1_key)
    if mtd is None and m1 is None:
        miss = [mtd_key] + ([m1_key] if m1_key else [])
        return _na(key, label, miss, f"Direct: {mtd_key}" + (f", {m1_key}" if m1_key else ""))
    return _make_metric(
        key,
        label,
        mtd,
        m1,
        value_type="Direct",
        source_fields=sources,
        formula=f"Direct: {', '.join(sources)}",
    )


def _calc_from_pairs(
    raw: dict[str, Any],
    key: str,
    label: str,
    num_mtd: str,
    num_m1: str | None,
    den_mtd: str,
    den_m1: str | None,
    *,
    as_pct: bool = False,
) -> dict[str, Any]:
    nm, n1, src_n = _pair(raw, num_mtd, num_m1)
    dm, d1, src_d = _pair(raw, den_mtd, den_m1)

    if nm is None or dm is None:
        return _na(
            key,
            label,
            [num_mtd, den_mtd],
            f"({num_mtd}/{den_mtd})" + (" × 100" if as_pct else ""),
        )

    mtd = _pct(nm, dm) if as_pct else _div(nm, dm)
    m1 = None
    if n1 is not None and d1 is not None:
        m1 = _pct(n1, d1) if as_pct else _div(n1, d1)

    if mtd is not None and not as_pct and key != "roas":
        mtd = round(mtd, 2)
    if m1 is not None and not as_pct and key != "roas":
        m1 = round(m1, 2)

    op = f"({num_mtd}/{den_mtd})" + (" × 100" if as_pct else "")
    src = list(dict.fromkeys(src_n + src_d))
    return _make_metric(
        key,
        label,
        mtd,
        m1,
        value_type="Calculated",
        source_fields=src,
        formula=f"Calculated: {op}",
    )


def _video_gmv_pair(raw: dict[str, Any]) -> tuple[float | None, float | None, list[str]]:
    mtd, m1, src = _pair(raw, K_VIDEO_GMV_MTD, K_VIDEO_GMV_M1)
    if mtd is not None or m1 is not None:
        return mtd, m1, src
    adgmv_m, adgmv_m1, _ = _pair(raw, K_ADGMV_MTD, K_ADGMV_M1)
    pct_m = _num(raw.get(VIDEO_GMV_CONTRI_MTD))
    pct_m1 = _num(raw.get(VIDEO_GMV_CONTRI_M1))
    sources = []
    if pct_m is not None and adgmv_m is not None:
        mtd = round(adgmv_m * pct_m / 100, 2)
        sources.extend([VIDEO_GMV_CONTRI_MTD, resolve_raw_column(raw, K_ADGMV_MTD) or K_ADGMV_MTD])
    if pct_m1 is not None and adgmv_m1 is not None:
        m1 = round(adgmv_m1 * pct_m1 / 100, 2)
        sources.extend([VIDEO_GMV_CONTRI_M1, resolve_raw_column(raw, K_ADGMV_M1) or K_ADGMV_M1])
    return mtd, m1, sources


def _shop_info(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _info(raw, "shop_id", "Shop ID", "Shop ID"),
        _info(raw, "shop_name", "Shop Name", "Shop Name"),
        _info(raw, "managed_tier", "Managed Tier", "Managed Tier"),
        _info(raw, "bu", "BU", "BU2"),
        _info(raw, "lead", "Lead", "Lead"),
        _info(raw, "rm_kam", "RM/KAM", "RM/KAM"),
        _info(raw, "bd_category", "BD Category", "BD Category"),
        _info(raw, "bi_category", "BI Category", "BI Category"),
        _info(raw, "shop_link", "Shop Link", "Shop Link"),
        _info(raw, "seller_penalty_points", "Seller Penalty Points", "Seller Penalty Points"),
        _direct(raw, "mtd_fsp", "MTD FSP", "mtd_fsp", "m1_fsp"),
        _direct(raw, "mtd_pp", "MTD PP", "mtd_pp", "m1_pp"),
    ]


def _commercial(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _direct(raw, "adgmv", "ADGMV", K_ADGMV_MTD, K_ADGMV_M1),
        _direct(raw, "ado", "ADO", K_ADO_MTD, K_ADO_M1),
        _direct(raw, "uv", "UV", K_UV_MTD, K_UV_M1),
    ]


def _paid_ads(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _direct(raw, "ads_spend", "Ads Spend", K_ADS_EXP_MTD, K_ADS_EXP_M1),
        _direct(raw, "ads_gmv", "Ads GMV", K_ADS_GMV_MTD, K_ADS_GMV_M1),
        _direct(raw, "ads_adopted", "Ads Adopted", K_ADS_ADOPT_MTD, K_ADS_ADOPT_M1),
        _calc_from_pairs(raw, "roas", "ROAS", K_ADS_GMV_MTD, K_ADS_GMV_M1, K_ADS_EXP_MTD, K_ADS_EXP_M1),
        _calc_from_pairs(
            raw, "take_rate", "Take Rate", K_ADS_EXP_MTD, K_ADS_EXP_M1, K_ADGMV_MTD, K_ADGMV_M1, as_pct=True
        ),
        _calc_from_pairs(
            raw, "adg_pct", "Adg%", K_ADS_GMV_MTD, K_ADS_GMV_M1, K_ADGMV_MTD, K_ADGMV_M1, as_pct=True
        ),
    ]


def _mpa(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _direct(raw, "mpa_gmv", "MPA GMV", K_MPA_GMV_MTD, K_MPA_GMV_M1),
        _calc_from_pairs(
            raw,
            "take_rate",
            "MPA Take Rate",
            K_MPA_EXP_MTD,
            K_MPA_EXP_M1,
            K_ADGMV_MTD,
            K_ADGMV_M1,
            as_pct=True,
        ),
    ]


def _ams(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _direct(raw, "ams_adgmv", "AMS ADGMV", K_AMS_GMV_MTD, K_AMS_GMV_M1),
        _direct(raw, "ams_spend", "AMS Spend", K_AMS_EXP_MTD, K_AMS_EXP_M1),
        _direct(raw, "ams_adopted", "AMS Adopted", K_AMS_ADOPT_MTD, K_AMS_ADOPT_M1),
        _calc_from_pairs(raw, "roas", "ROAS", K_AMS_GMV_MTD, K_AMS_GMV_M1, K_AMS_EXP_MTD, K_AMS_EXP_M1),
        _calc_from_pairs(
            raw, "take_rate", "Take Rate", K_AMS_EXP_MTD, K_AMS_EXP_M1, K_ADGMV_MTD, K_ADGMV_M1, as_pct=True
        ),
    ]


def _livestream(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _direct(raw, "seller_ls_hrs", "Seller LS Hrs", K_LS_HRS_MTD, K_LS_HRS_M1),
        _direct(raw, "ls_adgmv", "LS ADGMV", K_LS_GMV_MTD, K_LS_GMV_M1),
        _calc_from_pairs(
            raw,
            "seller_ls_adg_pct",
            "Seller LS Adg%",
            K_LS_GMV_MTD,
            K_LS_GMV_M1,
            K_ADGMV_MTD,
            K_ADGMV_M1,
            as_pct=True,
        ),
    ]


def _video_adgmv_metric(raw: dict[str, Any]) -> dict[str, Any]:
    vm, v1, src = _video_gmv_pair(raw)
    if vm is None and v1 is None:
        return _na(
            "video_adgmv",
            "Video ADGMV",
            [K_VIDEO_GMV_MTD, VIDEO_GMV_CONTRI_MTD],
            f"Direct: {K_VIDEO_GMV_MTD} or derived from {VIDEO_GMV_CONTRI_MTD}",
        )
    growth = calculate_growth(vm, v1)
    return _make_metric(
        "video_adgmv",
        "Video ADGMV",
        vm,
        v1,
        value_type="Direct" if K_VIDEO_GMV_MTD in str(src) else "Calculated",
        source_fields=src,
        formula=f"Video ADGMV from {', '.join(src)}",
    )


def _video(raw: dict[str, Any]) -> list[dict[str, Any]]:
    vm, v1, vsrc = _video_gmv_pair(raw)
    adg_row = (
        _make_metric(
            "adg_pct",
            "Adg%",
            _pct(vm, _num(_raw(raw, K_ADGMV_MTD))),
            _pct(v1, _num(_raw(raw, K_ADGMV_M1))) if v1 is not None else None,
            value_type="Calculated",
            source_fields=list(dict.fromkeys(vsrc + [_col(raw, K_ADGMV_MTD) or K_ADGMV_MTD])),
            formula=f"Video ADGMV / ADGMV",
        )
        if vm is not None or v1 is not None
        else _calc_from_pairs(
            raw, "adg_pct", "Adg%", K_VIDEO_GMV_MTD, K_VIDEO_GMV_M1, K_ADGMV_MTD, K_ADGMV_M1, as_pct=True
        )
    )
    return [_video_adgmv_metric(raw), adg_row, _direct(raw, "new_uploads", "New Uploads", K_NEW_UPLOADS_MTD, K_NEW_UPLOADS_M1)]


def _mdv(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _direct(raw, "mdv_adgmv", "MDV ADGMV", K_MDV_GMV_MTD, K_MDV_GMV_M1),
        _direct(raw, "gmv_adoption_pct", "GMV Adoption %", K_MDV_ADOPT_MTD, K_MDV_ADOPT_M1),
        _calc_from_pairs(
            raw, "adg_pct", "Adg%", K_MDV_GMV_MTD, K_MDV_GMV_M1, K_ADGMV_MTD, K_ADGMV_M1, as_pct=True
        ),
    ]


def _atc(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _direct(raw, "dday_submitted", "DDay Submitted", "adg_submitted1"),
        _direct(raw, "dday_approved", "DDay Approved", "adg_approved1"),
        _direct(raw, "dday_sku", "DDay SKU Count", "ContingencySKU1"),
        _direct(raw, "payday15_submitted", "Payday-15 Submitted", "adg_submitted2"),
        _direct(raw, "payday15_approved", "Payday-15 Approved", "adg_approved2"),
        _direct(raw, "payday15_sku", "Payday-15 SKU Count", "ContingencySKU2"),
        _direct(raw, "payday30_submitted", "Payday-30 Submitted", "adg_submitted3"),
        _direct(raw, "payday30_approved", "Payday-30 Approved", "adg_approved3"),
        _direct(raw, "payday30_sku", "Payday-30 SKU Count", "ContingencySKU3"),
    ]


def _price_bidding(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _direct(raw, "eligible_sku", "Eligible SKU", "Eligible_SKU"),
        _direct(raw, "bidded_sku", "Bidded SKU", "Bidded_SKU"),
        _calc_from_pairs(raw, "bid_rate", "Bid Rate", "Bidded_SKU", None, "Eligible_SKU", None, as_pct=True),
    ]


def _fbs(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _direct(raw, "fbs_gmv", "FBS GMV", K_FBS_GMV_MTD, K_FBS_GMV_M1),
        _direct(raw, "fbs_ado", "FBS ADO", K_FBS_ADO_MTD, K_FBS_ADO_M1),
    ]


SECTION_RESOLVERS: list[tuple[str, str, MetricFn]] = [
    ("shop_info", "Shop Info", _shop_info),
    ("commercial", "Commercial Overview", _commercial),
    ("paid_ads", "Paid Ads", _paid_ads),
    ("mpa", "MPA", _mpa),
    ("ams", "AMS", _ams),
    ("livestream", "Livestream", _livestream),
    ("video", "Video", _video),
    ("mdv", "MDV", _mdv),
    ("atc", "ATC Participation", _atc),
    ("price_bidding", "Price Bidding", _price_bidding),
    ("fbs", "FBS", _fbs),
]


def resolve_sections_from_raw(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"key": key, "title": title, "metrics": resolver(raw)}
        for key, title, resolver in SECTION_RESOLVERS
    ]


def collect_missing_fields(sections: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for section in sections:
        for m in section.get("metrics", []):
            if m.get("valueType") != "N/A":
                continue
            for field in m.get("missingFields") or []:
                if field in seen:
                    continue
                seen.add(field)
                out.append(
                    {
                        "field": field,
                        "metric": m.get("label", ""),
                        "section": section.get("title", ""),
                        "reason": m.get("calculationFormula", "Missing in raw row"),
                    }
                )
    return out


def metric_lookup(sections: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for section in sections:
        sk = section["key"]
        out[sk] = {m["key"]: m for m in section.get("metrics", [])}
    return out


def build_dashboard_from_raw(raw: dict[str, Any]) -> dict[str, Any]:
    sections = resolve_sections_from_raw(raw)
    return {
        "sections": sections,
        "metricIndex": metric_lookup(sections),
        "missingFieldsSummary": collect_missing_fields(sections),
    }


def shop_info_from_raw(raw: dict[str, Any], shop_id: str, shop_name: str) -> dict[str, str]:
    """Map shop metadata from AI data columns."""
    return {
        "shop_id": shop_id,
        "shop_name": shop_name or str(_raw(raw, "Shop Name") or shop_id).strip(),
        "tier": str(_raw(raw, "Managed Tier") or "").strip(),
        "category": str(_raw(raw, "BD Category") or _raw(raw, "BI Category") or "").strip(),
        "bu": str(_raw(raw, "BU2") or _raw(raw, "BU") or "").strip(),
        "lead": str(_raw(raw, "Lead") or "").strip(),
        "rm_kam": str(_raw(raw, "RM/KAM") or "").strip(),
        "shop_link": str(_raw(raw, "Shop Link") or "").strip(),
        "bi_category": str(_raw(raw, "BI Category") or "").strip(),
    }
