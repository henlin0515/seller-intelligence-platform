"""One-off mapping audit report — does not change resolver logic."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from seller.ai_data_fields import AI_DATA_FIELD_MAP
from seller.metric_resolver import (
    K_ADGMV_M1,
    K_ADGMV_MTD,
    K_ADO_M1,
    K_ADO_MTD,
    K_ADS_ADOPT_M1,
    K_ADS_ADOPT_MTD,
    K_ADS_EXP_M1,
    K_ADS_EXP_MTD,
    K_ADS_GMV_M1,
    K_ADS_GMV_MTD,
    K_AMS_ADOPT_M1,
    K_AMS_ADOPT_MTD,
    K_AMS_EXP_M1,
    K_AMS_EXP_MTD,
    K_AMS_GMV_M1,
    K_AMS_GMV_MTD,
    K_FBS_ADO_M1,
    K_FBS_ADO_MTD,
    K_LS_GMV_M1,
    K_LS_GMV_MTD,
    K_LS_HRS_M1,
    K_LS_HRS_MTD,
    K_MDV_ADOPT_M1,
    K_MDV_ADOPT_MTD,
    K_MDV_GMV_M1,
    K_MDV_GMV_MTD,
    K_MPA_ADOPT_M1,
    K_MPA_ADOPT_MTD,
    K_MPA_EXP_M1,
    K_MPA_EXP_MTD,
    K_MPA_GMV_M1,
    K_MPA_GMV_MTD,
    K_NEW_UPLOADS_M1,
    K_NEW_UPLOADS_MTD,
    K_UV_M1,
    K_UV_MTD,
    K_VIDEO_GMV_M1,
    K_VIDEO_GMV_MTD,
    VIDEO_GMV_CONTRI_M1,
    VIDEO_GMV_CONTRI_MTD,
    _col,
    _num,
    _raw,
    _value_present,
    _video_gmv_pair,
    build_dashboard_from_raw,
    resolve_raw_column,
)
from seller.raw_data import get_raw_shop_row
from seller.sheets_cache import refresh

Spec = tuple[str, str, str | tuple, str]


def sheet_header(logical_key: str) -> str:
    spec = AI_DATA_FIELD_MAP.get(logical_key, logical_key)
    if isinstance(spec, str):
        return spec
    return " | ".join(spec)


def classify_logical(logical_key: str, raw: dict) -> str | None:
    col = resolve_raw_column(raw, logical_key)
    if col is None:
        return "field mapping not found"
    if not _value_present(raw.get(col)):
        return "field empty"
    return None


def raw_cell(logical_key: str, raw: dict) -> tuple[str | None, str | None, Any]:
    col = resolve_raw_column(raw, logical_key)
    if col is None:
        return logical_key, None, None
    val = raw.get(col)
    n = _num(val)
    if n is not None:
        return logical_key, col, n
    if _value_present(val):
        return logical_key, col, str(val).strip()
    return logical_key, col, None


def build_specs() -> list[Spec]:
    specs: list[Spec] = []

    def info(label: str, lk: str) -> None:
        specs.append(("Shop Info", label, lk, "info"))

    def direct(section: str, label: str, mtd: str, m1: str | None = None) -> None:
        specs.append((section, f"{label} MTD", mtd, "direct"))
        if m1:
            specs.append((section, f"{label} M-1", m1, "direct"))

    def calc(section: str, label: str, num: str, den: str, pct: bool = False) -> None:
        specs.append((section, label, ("calc_pct" if pct else "calc", num, den), "calc"))

    info("Shop ID", "Shop ID")
    info("Shop Name", "Shop Name")
    info("Managed Tier", "Managed Tier")
    info("BU", "BU2")
    info("Lead", "Lead")
    info("BD Category", "BD Category")
    info("BI Category", "BI Category")

    direct("Commercial Overview", "ADGMV", K_ADGMV_MTD, K_ADGMV_M1)
    direct("Commercial Overview", "ADO", K_ADO_MTD, K_ADO_M1)
    direct("Commercial Overview", "UV", K_UV_MTD, K_UV_M1)

    direct("Paid Ads", "Ads Spend", K_ADS_EXP_MTD, K_ADS_EXP_M1)
    direct("Paid Ads", "Ads GMV", K_ADS_GMV_MTD, K_ADS_GMV_M1)
    direct("Paid Ads", "Ads Adopted", K_ADS_ADOPT_MTD, K_ADS_ADOPT_M1)
    calc("Paid Ads", "ROAS MTD", K_ADS_GMV_MTD, K_ADS_EXP_MTD)
    calc("Paid Ads", "ROAS M-1", K_ADS_GMV_M1, K_ADS_EXP_M1)
    calc("Paid Ads", "Take Rate MTD", K_ADS_EXP_MTD, K_ADGMV_MTD, pct=True)
    calc("Paid Ads", "Take Rate M-1", K_ADS_EXP_M1, K_ADGMV_M1, pct=True)
    calc("Paid Ads", "Adg% MTD", K_ADS_GMV_MTD, K_ADGMV_MTD, pct=True)
    calc("Paid Ads", "Adg% M-1", K_ADS_GMV_M1, K_ADGMV_M1, pct=True)

    direct("MPA + CPAS", "MPA GMV", K_MPA_GMV_MTD, K_MPA_GMV_M1)
    direct("MPA + CPAS", "MPA Spend", K_MPA_EXP_MTD, K_MPA_EXP_M1)
    direct("MPA + CPAS", "Adopted GMV%", K_MPA_ADOPT_MTD, K_MPA_ADOPT_M1)
    calc("MPA + CPAS", "ROAS MTD", K_MPA_GMV_MTD, K_MPA_EXP_MTD)
    calc("MPA + CPAS", "Take Rate MTD", K_MPA_EXP_MTD, K_ADGMV_MTD, pct=True)
    calc("MPA + CPAS", "Adg% MTD", K_MPA_GMV_MTD, K_ADGMV_MTD, pct=True)

    direct("AMS", "AMS ADGMV", K_AMS_GMV_MTD, K_AMS_GMV_M1)
    direct("AMS", "AMS Spend", K_AMS_EXP_MTD, K_AMS_EXP_M1)
    direct("AMS", "AMS Adopted", K_AMS_ADOPT_MTD, K_AMS_ADOPT_M1)
    calc("AMS", "ROAS MTD", K_AMS_GMV_MTD, K_AMS_EXP_MTD)
    calc("AMS", "Take Rate MTD", K_AMS_EXP_MTD, K_ADGMV_MTD, pct=True)

    direct("Livestream", "Seller LS Hrs", K_LS_HRS_MTD, K_LS_HRS_M1)
    direct("Livestream", "LS ADGMV", K_LS_GMV_MTD, K_LS_GMV_M1)
    calc("Livestream", "Seller LS Adg% MTD", K_LS_GMV_MTD, K_ADGMV_MTD, pct=True)

    specs.append(("Video", "Video ADGMV MTD", "video_mtd", "video"))
    specs.append(("Video", "Video ADGMV M-1", "video_m1", "video"))
    specs.append(("Video", "Adg% MTD", "video_adg_mtd", "video_adg"))
    direct("Video", "New Uploads", K_NEW_UPLOADS_MTD, K_NEW_UPLOADS_M1)

    direct("MDV", "MDV ADGMV", K_MDV_GMV_MTD, K_MDV_GMV_M1)
    direct("MDV", "GMV Adoption %", K_MDV_ADOPT_MTD, K_MDV_ADOPT_M1)
    calc("MDV", "Adg% MTD", K_MDV_GMV_MTD, K_ADGMV_MTD, pct=True)

    for label, lk in [
        ("DDay Submitted", "adg_submitted1"),
        ("DDay Approved", "adg_approved1"),
        ("DDay SKU Count", "ContingencySKU1"),
        ("Payday-15 Submitted", "adg_submitted2"),
        ("Payday-15 Approved", "adg_approved2"),
        ("Payday-15 SKU Count", "ContingencySKU2"),
        ("Payday-30 Submitted", "adg_submitted3"),
        ("Payday-30 Approved", "adg_approved3"),
        ("Payday-30 SKU Count", "ContingencySKU3"),
    ]:
        specs.append(("ATC Participation", f"{label} MTD", lk, "direct"))

    specs.append(("Price Bidding", "Eligible SKU MTD", "Eligible_SKU", "direct"))
    specs.append(("Price Bidding", "Bidded SKU MTD", "Bidded_SKU", "direct"))
    calc("Price Bidding", "Bid Rate MTD", "Bidded_SKU", "Eligible_SKU", pct=True)

    direct("FBS", "FBS ADO", K_FBS_ADO_MTD, K_FBS_ADO_M1)
    calc("FBS", "FBS ADO% MTD", K_FBS_ADO_MTD, K_ADO_MTD, pct=True)

    return specs


SPECS = build_specs()


def calc_value(raw: dict, num_k: str, den_k: str, pct: bool) -> tuple[Any, list[tuple[str, str | None, Any, str | None]]]:
    parts = []
    nums = []
    dens = []
    for lk in (num_k, den_k):
        src, col, val = raw_cell(lk, raw)
        reason = classify_logical(lk, raw)
        parts.append((lk, col, val, reason))
        if lk == num_k:
            nums.append(val)
        else:
            dens.append(val)
    nv, dv = nums[0], dens[0]
    if nv is None or dv is None:
        return "N/A", parts
    if dv == 0:
        return "N/A", parts
    out = (nv / dv) * 100 if pct else nv / dv
    return round(out, 2), parts


def audit_shop(shop_id: str, shop_label: str, raw: dict) -> None:
    resolved = build_dashboard_from_raw(raw)
    idx_na = {
        (s["title"], m["label"]): m
        for s in resolved["sections"]
        for m in s["metrics"]
        if m.get("valueType") == "N/A"
    }

    print("=" * 72)
    print(f"{shop_label} (Shop ID {shop_id})")
    print("=" * 72)
    print()

    na_rows: list[dict] = []

    for section, display, spec, kind in SPECS:
        print(display)
        if kind == "info" or kind == "direct":
            lk = str(spec)
            src, col, val = raw_cell(lk, raw)
            reason = classify_logical(lk, raw)
            print(f"source: {lk}")
            print(f"sheet column: {sheet_header(lk)}")
            if col:
                print(f"raw key: {col!r}")
            if reason:
                print(f"value: N/A")
                print(f"reason: {reason}")
                na_rows.append(
                    {
                        "section": section,
                        "metric": display,
                        "logical": lk,
                        "reason": reason,
                        "expected": sheet_header(lk),
                    }
                )
            else:
                print(f"value: {val}")
            print()
            continue

        if kind == "calc":
            assert isinstance(spec, tuple)
            _, num_k, den_k = spec
            pct = spec[0] == "calc_pct"
            val, parts = calc_value(raw, num_k, den_k, pct)
            op = f"{num_k} / {den_k}" + (" × 100" if pct else "")
            print(f"source: {op}")
            for lk, col, v, reason in parts:
                line = f"  {lk}"
                if col:
                    line += f" → {col!r}"
                line += f" = {v!r}"
                if reason:
                    line += f" ({reason})"
                print(line)
            print(f"value: {val}")
            if val == "N/A":
                reasons = [f"{lk}: {r}" for lk, _, _, r in parts if r]
                if not reasons:
                    reasons = ["calculation blocked (missing operand or zero denominator)"]
                na_rows.append(
                    {
                        "section": section,
                        "metric": display,
                        "logical": op,
                        "reason": "; ".join(reasons),
                        "expected": "",
                    }
                )
            print()
            continue

        if kind == "video":
            vm, v1, src = _video_gmv_pair(raw)
            val = vm if spec == "video_mtd" else v1
            print("source: mtd_video_adg (or derived: VIdeo GMV Contri % × Total ADG)")
            if src:
                for h in src:
                    print(f"  sheet field used: {h!r} = {raw.get(h)!r}")
            if val is None:
                print("value: N/A")
                na_rows.append(
                    {
                        "section": section,
                        "metric": display,
                        "logical": "mtd_video_adg / VIdeo GMV Contri % M + mtd_adg",
                        "reason": "field mapping not found or derived inputs missing",
                        "expected": "Video ADGMV M | VIdeo GMV Contri % M + Total ADG M",
                    }
                )
            else:
                print(f"value: {val}")
            print()
            continue

        if kind == "video_adg":
            vm, _, vsrc = _video_gmv_pair(raw)
            adgmv = _num(_raw(raw, K_ADGMV_MTD))
            pct = round(vm / adgmv * 100, 2) if vm is not None and adgmv else None
            print("source: Video ADGMV MTD / mtd_adg")
            print(f"value: {pct if pct is not None else 'N/A'}")
            print()

    print("--- Dashboard resolver N/A metrics (from current logic) ---")
    for s in resolved["sections"]:
        for m in s["metrics"]:
            if m.get("valueType") != "N/A":
                continue
            miss = m.get("missingFields") or []
            for lk in miss:
                reason = classify_logical(lk, raw)
                if not reason and m.get("mtdValue") is None:
                    reason = "field empty or calculation blocked"
                na_rows.append(
                    {
                        "section": s["title"],
                        "metric": m["label"],
                        "logical": lk,
                        "reason": reason or "calculation blocked",
                        "expected": sheet_header(lk),
                    }
                )
            if not miss:
                na_rows.append(
                    {
                        "section": s["title"],
                        "metric": m["label"],
                        "logical": m.get("calculationFormula", ""),
                        "reason": "calculation blocked",
                        "expected": "",
                    }
                )

    print("--- N/A summary (deduplicated) ---")
    seen = set()
    for row in na_rows:
        key = (row["section"], row["metric"], row["logical"], row["reason"])
        if key in seen:
            continue
        seen.add(key)
        print(f"[{row['section']}] {row['metric']}")
        print(f"  logical: {row['logical']}")
        if row.get("expected"):
            print(f"  expected column(s): {row['expected']}")
        print(f"  reason: {row['reason']}")
        print()


def main() -> None:
    refresh(force=True)
    for sid, label in [("19100527", "Mumu PH"), ("625975", "Watch District PH")]:
        entry = get_raw_shop_row(sid)
        if not entry:
            print(f"Shop {sid} not found")
            continue
        audit_shop(sid, label, entry["raw"])


if __name__ == "__main__":
    main()
