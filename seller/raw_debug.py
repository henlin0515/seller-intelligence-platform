"""
Temporary raw seller row debug payload (sheet column order, no metrics).
"""

from __future__ import annotations

from typing import Any

from seller.raw_data import get_raw_shop_row
from seller.sheets_cache import get_column_schema, get_load_summary


def _is_internal_raw_key(key: str) -> bool:
    return key.startswith("_tab.")


def build_ordered_raw_rows(
    raw: dict[str, Any],
    column_schema: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sheet columns in original order, then extra rawData keys not in schema."""
    rows: list[dict[str, Any]] = []
    schema_keys: set[str] = set()

    for col in column_schema:
        key = col.get("header_key", "")
        schema_keys.add(key)
        rows.append(
            {
                "sort_order": col.get("index", len(rows)),
                "column_index": col.get("index"),
                "column_letter": col.get("column_letter", ""),
                "header_name": col.get("sheet_header", key),
                "raw_key": key,
                "value": raw.get(key, ""),
                "source": "ai_data_column",
            }
        )

    extras = [
        k
        for k in raw.keys()
        if k not in schema_keys and not _is_internal_raw_key(k)
    ]
    extras.sort(key=lambda x: x.lower())
    for i, key in enumerate(extras):
        rows.append(
            {
                "sort_order": 10_000 + i,
                "column_index": None,
                "column_letter": "",
                "header_name": "(extra key)",
                "raw_key": key,
                "value": raw[key],
                "source": "raw_extra",
            }
        )

    return rows


def get_raw_debug_payload(shop_id: str) -> dict[str, Any] | None:
    entry = get_raw_shop_row(shop_id)
    if not entry:
        return None

    raw = entry.get("raw") or {}
    schema = get_column_schema()
    summary = get_load_summary() or {}
    layout = summary.get("layout") or {}

    ordered_rows = build_ordered_raw_rows(raw, schema)

    return {
        "shop": {
            "shop_id": entry["shop_id"],
            "shop_name": entry.get("shop_name", ""),
            "tier": entry.get("tier", ""),
            "category": entry.get("category", ""),
        },
        "sheetName": summary.get("spreadsheet_title") or "AI DATA",
        "primaryTab": summary.get("primary_tab") or "AI DATA",
        "headerRow": layout.get("header_row", 6),
        "dataStartRow": layout.get("data_start_row", 7),
        "rawData": raw,
        "orderedRows": ordered_rows,
        "columnCount": len(schema),
        "rawKeyCount": len(raw),
        "debugMode": True,
    }
