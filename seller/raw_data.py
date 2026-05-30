"""
Seller raw rows: live Google Sheets cache (when enabled) or mock fallback.
"""

from __future__ import annotations

from typing import Any

from seller.google_sheets.config import is_configured

SHEET_NAME = "[Raw] Shop Level - Fashion (mirror)"

# Mock fallback when GOOGLE_SHEETS_ENABLED=false
RAW_SHOP_ROWS: list[dict[str, Any]] = [
    {
        "shop_id": "PH100234",
        "shop_name": "GlowBeauty Official",
        "tier": "A",
        "category": "Fashion",
        "raw": {
            "ADGMV_MTD": 1285000,
            "ADGMV_M1": 1150000,
            "ADO_MTD": 8420,
            "ADO_M1": 7980,
            "GMV_MTD": 1285000,
            "GMV_M1": 1150000,
            "Orders_MTD": 8420,
            "Orders_M1": 7980,
            "Buyers_MTD": 8420,
            "Buyers_M1": 7980,
            "Items_Sold_MTD": 15324,
            "Items_Sold_M1": 14284,
            "UV_MTD": 285000,
            "UV_M1": 262000,
            "CR_MTD": 2.95,
            "CR_M1": 3.05,
            "Days_MTD": 30,
            "Days_M1": 30,
            "Paid_Ads_GMV_MTD": 234000,
            "Paid_Ads_GMV_M1": 190000,
            "Paid_Ads_Spend_MTD": 27000,
            "Paid_Ads_Spend_M1": 26500,
            "MPA_CPAS_GMV_MTD": 83600,
            "MPA_CPAS_GMV_M1": 66700,
            "MPA_CPAS_Spend_MTD": 41100,
            "MPA_CPAS_Spend_M1": 40300,
            "MPA_CPAS_Adopted_GMV_MTD": 159300,
            "MPA_CPAS_Adopted_GMV_M1": 126500,
            "AMS_ADGMV_MTD": 185000,
            "AMS_ADGMV_M1": 142000,
            "AMS_GMV_MTD": 185000,
            "AMS_GMV_M1": 142000,
            "AMS_Cost_MTD": 20100,
            "AMS_Cost_M1": 17500,
            "AMS_Commission_MTD": 14800,
            "AMS_Commission_M1": 10650,
            "LS_GMV_MTD": 54000,
            "LS_GMV_M1": 35700,
            "Seller_LS_Hours_MTD": 48,
            "Seller_LS_Hours_M1": 36,
            "LS_Orders_MTD": 716,
            "LS_Orders_M1": 495,
            "Video_GMV_MTD": 74600,
            "Video_GMV_M1": 48300,
            "MDV_GMV_MTD": 122000,
            "MDV_GMV_M1": 92000,
            "MDV_Eligible_GMV_MTD": 1285000,
            "MDV_Eligible_GMV_M1": 1150000,
            "ATC_DDay_Participation_MTD": 1,
            "ATC_DDay_Participation_M1": 1,
            "ATC_Payday15_Participation_MTD": 0,
            "ATC_Payday15_Participation_M1": 1,
            "ATC_Payday30_Participation_MTD": 1,
            "ATC_Payday30_Participation_M1": 0,
            "ATC_Submitted_MTD": 24,
            "ATC_Submitted_M1": 20,
            "ATC_Approved_MTD": 18,
            "ATC_Approved_M1": 17,
            "ATC_SKU_Count_MTD": 156,
            "ATC_SKU_Count_M1": 148,
            "PB_Eligible_SKU_MTD": 320,
            "PB_Eligible_SKU_M1": 305,
            "PB_Bidded_SKU_MTD": 95,
            "PB_Bidded_SKU_M1": 110,
            "FBS_ADO_MTD": 1250,
            "FBS_ADO_M1": 1180,
        },
    },
]


def _use_live_cache() -> bool:
    if not is_configured():
        return False
    from seller.sheets_cache import is_loaded

    return is_loaded()


def search_raw_shops(query: str) -> list[dict[str, str]]:
    if is_configured():
        from seller.sheets_cache import is_loaded, search_shops

        if is_loaded():
            return search_shops(query)
        return []

    q = query.strip().lower()
    if not q:
        return []
    out = []
    for row in RAW_SHOP_ROWS:
        if q in row["shop_id"].lower() or q in row["shop_name"].lower():
            out.append(
                {
                    "shop_id": row["shop_id"],
                    "shop_name": row["shop_name"],
                    "tier": row.get("tier", ""),
                    "category": row.get("category", ""),
                }
            )
    return out


def get_raw_shop_row(shop_id: str) -> dict[str, Any] | None:
    if is_configured():
        from seller.sheets_cache import entry_to_raw_row, lookup_shop

        entry = lookup_shop(shop_id)
        if entry:
            return entry_to_raw_row(entry)
        return None

    for row in RAW_SHOP_ROWS:
        if row["shop_id"].lower() == shop_id.strip().lower():
            return row
    return None
