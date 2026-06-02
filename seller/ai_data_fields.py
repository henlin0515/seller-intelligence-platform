"""
Map dashboard logical fields to live AI DATA sheet column headers (row 6).
Falls back to logical key if present in rawData.
"""

from __future__ import annotations

from typing import Any

# logical_key -> AI DATA header name(s), first match wins
AI_DATA_FIELD_MAP: dict[str, str | tuple[str, ...]] = {
    # Shop info
    "Shop ID": "Shop ID",
    "Shop Name": "Shop Name",
    "Managed Tier": "Managed Tier",
    "BU2": ("BU2", "BU"),
    "Lead": "Lead",
    "RM/KAM": ("May RM/KAM", "RM/KAM", "RM / KAM"),
    "Shop Link": "Shop Link",
    "Seller Penalty Points": "Seller Penalty Points",
    "BD Category": ("BD Category", "BD Category_2"),
    "BI Category": "BI Category",
    "mtd_fsp": ("mtd_fsp", "MTD FSP", "FSP M"),
    "m1_fsp": ("m1_fsp", "M1 FSP", "FSP M-1"),
    "mtd_pp": ("mtd_pp", "MTD PP"),
    "m1_pp": ("m1_pp", "M1 PP"),
    # Commercial
    "mtd_adg": "Total ADG M",
    "m1_adg": "Total ADG M-1",
    "mtd_ado": "Total ADO M",
    "m1_ado": "Total ADO M-1",
    "mtd_uv": "PDP UV M",
    "m1_uv": "PDP UV M-1",
    # Paid Ads
    "mtd_ads_exp": "Daily Net Ads Expense M",
    "m1_ads_exp": "Daily Net Ads Expense M-1",
    "mtd_ads_adg": "Ads ADGMV M",
    "m1_ads_adg": "Ads ADGMV M-1",
    "mtd_ads_adopted": ("mtd_ads_adopted", "Paid Ads Active\nM", "Paid Ads Active M"),
    "m1_ads_adopted": ("m1_ads_adopted", "Paid Ads Active\nM-1", "Paid Ads Active M-1"),
    # MPA + CPAS (not present in current mirror columns — kept for when added)
    "mtd_mpa_adg": ("mtd_mpa_adg", "MPA ADGMV M"),
    "m1_mpa_adg": ("m1_mpa_adg", "MPA ADGMV M-1"),
    "mtd_mpa_exp": ("mtd_mpa_exp", "Daily MPA Expense M"),
    "m1_mpa_exp": ("m1_mpa_exp", "Daily MPA Expense M-1"),
    "mtd_mpa_gmvcontri": ("mtd_mpa_gmvcontri", "MPA GMV Contri % M"),
    "m1_mpa_gmvcontri": ("m1_mpa_gmvcontri", "MPA GMV Contri % M-1"),
    # AMS
    "mtd_ams_adg": ("mtd_ams_adg", "AMS ADGMV M"),
    "m1_ams_adg": ("m1_ams_adg", "AMS ADGMV M-1"),
    "mtd_ams_exp": "Daily AMS Expense M",
    "m1_ams_exp": "Daily AMS Expense M-1",
    # Livestream
    "mtd_ls_hrs": ("mtd_ls_hrs", "Live Xtra Active MTD"),
    "m1_ls_hrs": ("m1_ls_hrs", "Live Xtra Active M-1"),
    "mtd_ls_adg": ("mtd_ls_adg", "LS ADGMV M"),
    "m1_ls_adg": ("m1_ls_adg", "LS ADGMV M-1"),
    # Video
    "mtd_video_adg": ("mtd_video_adg", "Video ADGMV M"),
    "m1_video_adg": ("m1_video_adg", "Video ADGMV M-1"),
    "mtd_new_uploads": ("mtd_new_uploads", "New Videos Growth (%)"),
    "m1_new_uploads": ("m1_new_uploads", "New Videos M-1"),
    # MDV
    "mtd_mdv_adg": "MDV ADGMV M",
    "m1_mdv_adg": "MDV ADGMV M-1",
    "mtd_mdv_adgcov": ("mtd_mdv_adgcov", "MDV GMV Adoption % M", "MDV ADGCOV M"),
    "m1_mdv_adgcov": ("m1_mdv_adgcov", "MDV GMV Adoption % M-1"),
    # ATC
    "adg_submitted1": ("adg_submitted1", "DDay Submitted"),
    "adg_approved1": ("adg_approved1", "DDay Approved"),
    "ContingencySKU1": ("ContingencySKU1", "DDay SKU Count"),
    "adg_submitted2": ("adg_submitted2", "Payday-15 Submitted"),
    "adg_approved2": ("adg_approved2", "Payday-15 Approved"),
    "ContingencySKU2": ("ContingencySKU2", "Payday-15 SKU Count"),
    "adg_submitted3": ("adg_submitted3", "Payday-30 Submitted"),
    "adg_approved3": ("adg_approved3", "Payday-30 Approved"),
    "ContingencySKU3": ("ContingencySKU3", "Payday-30 SKU Count"),
    # Price bidding
    "Eligible_SKU": ("Eligible_SKU", "Eligible SKU"),
    "Bidded_SKU": ("Bidded_SKU", "Bidded SKU"),
    # FBS
    "mtd_fbs_gmv": ("mtd_fbs_gmv", "FBS GMV M", "FBS ADGMV M"),
    "m1_fbs_gmv": ("m1_fbs_gmv", "FBS GMV M-1", "FBS ADGMV M-1"),
    "mtd_fbs_ado": ("mtd_fbs_ado", "FBS ADO M"),
    "m1_fbs_ado": ("m1_fbs_ado", "FBS ADO M-1"),
}

# Video GMV contribution % when absolute Video GMV column is absent
VIDEO_GMV_CONTRI_MTD = "VIdeo GMV Contri % M"
VIDEO_GMV_CONTRI_M1 = "VIdeo GMV Contri % M-1"


def resolve_raw_column(raw: dict[str, Any], logical_key: str) -> str | None:
    """Return the rawData key to use for a logical field."""
    spec = AI_DATA_FIELD_MAP.get(logical_key, logical_key)
    candidates = (spec,) if isinstance(spec, str) else spec
    for name in candidates:
        if name in raw:
            return name
    return None
