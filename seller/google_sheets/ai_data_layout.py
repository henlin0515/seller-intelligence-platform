"""
Fixed layout for mirror tab "AI DATA" (multi-row headers).
Row/column numbers are 1-based as in Google Sheets.
"""

from __future__ import annotations

import re
from typing import Any

PRIMARY_TAB_NAME = "AI DATA"
HEADER_ROW_1_BASED = 6
DATA_START_ROW_1_BASED = 7
SHOP_ID_COL_LETTER = "J"
SHOP_NAME_COL_LETTER = "K"
SHOP_ID_COL_INDEX = 9  # J, zero-based
SHOP_NAME_COL_INDEX = 10  # K, zero-based
SHOP_ID_HEADER = "Shop ID"
SHOP_NAME_HEADER = "Shop Name"

MERGE_STRATEGY_AI_DATA = (
    "ai_data_fixed_layout: primary tab AI DATA; header row 6; data from row 7; "
    "Shop ID column J (header 'Shop ID'); Shop Name column K; "
    "rawData[headerName]=cellValue for all columns"
)


def col_index_to_letter(index: int) -> str:
    """0-based column index to Excel letter (0=A, 9=J)."""
    n = index + 1
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _header_name(raw_header: str, col_index: int, used: dict[str, int]) -> str:
    name = (raw_header or "").strip()
    if not name:
        name = f"Column_{col_index_to_letter(col_index)}"
    key = name
    if key in used:
        used[key] += 1
        name = f"{key}_{used[key]}"
    else:
        used[key] = 1
    return name


def normalize_shop_id(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("#n/a", "n/a", "-", "", "#ref!"):
        return None
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def parse_ai_data_grid(grid: list[list[Any]]) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    """
    Parse AI DATA tab using fixed row 6 headers and row 7+ data.
    Each record maps header name -> cell value (all columns preserved).
    """
    header_idx = HEADER_ROW_1_BASED - 1
    data_start_idx = DATA_START_ROW_1_BASED - 1

    if len(grid) <= header_idx:
        raise ValueError("AI DATA tab has fewer rows than header row 6")

    header_row = grid[header_idx]
    max_cols = max(len(header_row), max((len(r) for r in grid[data_start_idx:]), default=0))
    used: dict[str, int] = {}
    headers: list[str] = []
    column_schema: list[dict[str, Any]] = []
    for j in range(max_cols):
        cell = header_row[j] if j < len(header_row) else ""
        sheet_header = str(cell).strip() or f"Column_{col_index_to_letter(j)}"
        header_key = _header_name(sheet_header, j, used)
        headers.append(header_key)
        column_schema.append(
            {
                "index": j,
                "column_letter": col_index_to_letter(j),
                "sheet_header": sheet_header,
                "header_key": header_key,
            }
        )

    shop_id_header = headers[SHOP_ID_COL_INDEX] if SHOP_ID_COL_INDEX < len(headers) else SHOP_ID_HEADER
    shop_name_header = (
        headers[SHOP_NAME_COL_INDEX] if SHOP_NAME_COL_INDEX < len(headers) else SHOP_NAME_HEADER
    )

    records: list[dict[str, Any]] = []
    for row in grid[data_start_idx:]:
        if not any(str(c).strip() for c in row):
            continue
        padded = list(row) + [""] * max(0, max_cols - len(row))
        shop_id_val = normalize_shop_id(
            padded[SHOP_ID_COL_INDEX] if SHOP_ID_COL_INDEX < len(padded) else None
        )
        if not shop_id_val:
            continue

        raw: dict[str, Any] = {}
        for j, header in enumerate(headers):
            raw[header] = padded[j] if j < len(padded) else ""

        shop_name = ""
        if SHOP_NAME_COL_INDEX < len(padded):
            shop_name = str(padded[SHOP_NAME_COL_INDEX] or "").strip()

        records.append(
            {
                "shop_id": shop_id_val,
                "shop_name": shop_name,
                "raw": raw,
            }
        )

    layout_meta = {
        "header_row": HEADER_ROW_1_BASED,
        "data_start_row": DATA_START_ROW_1_BASED,
        "shop_id_column": SHOP_ID_COL_LETTER,
        "shop_name_column": SHOP_NAME_COL_LETTER,
        "shop_id_col_index": SHOP_ID_COL_INDEX,
        "shop_name_col_index": SHOP_NAME_COL_INDEX,
        "shop_id_header": shop_id_header,
        "shop_name_header": shop_name_header,
        "header_count": len(headers),
        "data_rows_parsed": len(records),
        "column_schema": column_schema,
    }
    return headers, records, layout_meta


def build_sellers_from_ai_data(grid: list[list[Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Build seller cache entries keyed by Shop ID."""
    headers, records, layout_meta = parse_ai_data_grid(grid)
    sellers: dict[str, dict[str, Any]] = {}

    for rec in records:
        sid = rec["shop_id"]
        raw = dict(rec["raw"])
        raw[SHOP_ID_HEADER] = sid
        if rec.get("shop_name"):
            raw[SHOP_NAME_HEADER] = rec["shop_name"]
        raw["Shop ID"] = sid
        if rec.get("shop_name"):
            raw["Shop Name"] = rec["shop_name"]

        tier = str(raw.get("Managed Tier") or "").strip()
        category = str(raw.get("BD Category") or raw.get("BI Category") or "").strip()

        sellers[sid] = {
            "shop_id": sid,
            "shop_name": rec.get("shop_name") or str(raw.get("Shop Name") or sid).strip(),
            "tier": tier,
            "category": category,
            "raw": raw,
            "_source_tabs": [PRIMARY_TAB_NAME],
            "_shop_name_header": SHOP_NAME_HEADER,
        }

    column_keys: set[str] = set()
    for entry in sellers.values():
        column_keys.update(entry["raw"].keys())

    summary = {
        "merge_strategy": MERGE_STRATEGY_AI_DATA,
        "primary_tab": PRIMARY_TAB_NAME,
        "shop_id_field": SHOP_ID_HEADER,
        "shop_name_field": SHOP_NAME_HEADER,
        "layout": layout_meta,
        "tabs_discovered": [PRIMARY_TAB_NAME],
        "tabs_merged": [PRIMARY_TAB_NAME],
        "tabs_skipped": [],
        "tab_structures": [
            {
                "title": PRIMARY_TAB_NAME,
                "grid_rows": len(grid),
                "header_row": HEADER_ROW_1_BASED,
                "data_start_row": DATA_START_ROW_1_BASED,
                "header_count": len(headers),
                "data_rows": len(records),
                "shop_id_column": SHOP_ID_COL_LETTER,
                "shop_name_column": SHOP_NAME_COL_LETTER,
                "headers_sample": headers[:12],
            }
        ],
        "seller_count": len(sellers),
        "total_seller_rows_loaded": len(records),
        "total_grid_rows_read": len(grid),
        "total_columns_loaded": len(headers),
        "total_columns_merged": len(column_keys),
    }
    return sellers, summary
