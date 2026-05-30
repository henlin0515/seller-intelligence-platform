from __future__ import annotations

import logging
import re
from typing import Any

from seller.competitor_tracker.constants import COMPETITOR_TAB_NAME
from seller.google_sheets.client import try_get_sheets_client

logger = logging.getLogger("seller.competitor_tracker.sheet")

_HEADER_SHOP_ID = re.compile(r"shop\s*id", re.I)


def _cell(row: list[Any], idx: int) -> str:
    if idx >= len(row):
        return ""
    return str(row[idx] or "").strip()


def _is_header_row(row: list[Any]) -> bool:
    if not row:
        return False
    first = _cell(row, 0).lower()
    return bool(_HEADER_SHOP_ID.search(first))


def parse_competitor_grid(grid: list[list[Any]]) -> list[dict[str, str]]:
    """
    Parse COMPETITOR_TRACKER tab (columns A–D).

    A = Shop ID, B = Shop Name, C = Shopee competitor link, D = TikTok competitor link.
    Includes any row with Column C and/or Column D — TikTok is not required.
    """
    if not grid:
        return []

    start = 1 if _is_header_row(grid[0]) else 0
    competitors: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for offset, row in enumerate(grid[start:]):
        shop_id = _cell(row, 0)
        shop_name = _cell(row, 1)
        shopee_link = _cell(row, 2)  # Column C
        tiktok_link = _cell(row, 3)  # Column D
        if not shop_id and not shop_name and not shopee_link and not tiktok_link:
            continue
        if not shopee_link and not tiktok_link:
            continue
        if not shop_id:
            shop_id = shop_name or shopee_link or tiktok_link
        row_number = start + offset + 1
        if shop_id in seen_ids:
            shop_id = f"{shop_id}__row{row_number}"
        seen_ids.add(shop_id)
        competitors.append(
            {
                "row_number": str(row_number),
                "shop_id": shop_id,
                "shop_name": shop_name or shop_id,
                "shopee_link": shopee_link,
                "tiktok_link": tiktok_link,
            }
        )
    return competitors


def load_competitors_from_sheet() -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Load competitor rows from Google Sheets (standalone tab read)."""
    client = try_get_sheets_client()
    if client is None:
        return [], {
            "configured": False,
            "tab": COMPETITOR_TAB_NAME,
            "error": "Google Sheets is not configured or enabled.",
        }

    try:
        titles = client.list_worksheet_titles()
        if COMPETITOR_TAB_NAME not in titles:
            return [], {
                "configured": True,
                "tab": COMPETITOR_TAB_NAME,
                "error": f"Worksheet '{COMPETITOR_TAB_NAME}' not found in spreadsheet.",
                "tabs_available": titles[:20],
            }
        grid = client.fetch_worksheet_values(COMPETITOR_TAB_NAME)
        rows = parse_competitor_grid(grid)
        return rows, {
            "configured": True,
            "tab": COMPETITOR_TAB_NAME,
            "row_count": len(rows),
            "error": None,
        }
    except Exception as exc:
        logger.exception("Failed to load %s tab", COMPETITOR_TAB_NAME)
        return [], {
            "configured": True,
            "tab": COMPETITOR_TAB_NAME,
            "error": "Could not read competitor tracker sheet.",
            "_internal_error": str(exc),
        }
