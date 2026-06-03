"""Category → shop mapping from Google Sheet tab ``category raw``."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from seller.google_sheets.client import get_sheets_client
from seller.google_sheets.config import is_configured
from seller.google_sheets.exceptions import (
    GoogleSheetsNotConfiguredError,
    GoogleSheetsNotEnabledError,
)
from seller.intelligence.gp_shop_rm import normalize_shop_key

logger = logging.getLogger("seller.intelligence.category_raw")

DEFAULT_CATEGORY_RAW_TAB = "category raw"
MAX_CATEGORY_COLUMNS = 4

_cache: "CategoryRawIndex | None" = None
_cache_loaded_at: float | None = None
_lock = threading.RLock()
CACHE_TTL_SEC = int(os.getenv("CATEGORY_RAW_CACHE_TTL_SEC", "300"))


def category_raw_tab_name() -> str:
    return (os.getenv("GOOGLE_SHEET_CATEGORY_RAW_TAB") or DEFAULT_CATEGORY_RAW_TAB).strip()


def _cell(row: list[Any], index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index] or "").strip()


@dataclass
class CategoryRawIndex:
    tab: str
    categories: list[dict[str, Any]] = field(default_factory=list)

    @property
    def by_category(self) -> dict[str, list[str]]:
        return {c["name"]: list(c["shop_keys"]) for c in self.categories}


def parse_category_raw_rows(
    rows: list[list[Any]],
    *,
    tab: str = DEFAULT_CATEGORY_RAW_TAB,
    max_columns: int = MAX_CATEGORY_COLUMNS,
) -> CategoryRawIndex:
    """
    Parse category raw sheet: row 1 headers = category names (A–D);
    shop names below each header belong to that category.
    """
    if not rows:
        return CategoryRawIndex(tab=tab, categories=[])

    header = rows[0]
    columns: list[tuple[int, str]] = []
    for col_idx in range(min(max_columns, len(header))):
        name = _cell(header, col_idx)
        if name:
            columns.append((col_idx, name))

    shop_keys_by_name: dict[str, set[str]] = {name: set() for _, name in columns}
    for row in rows[1:]:
        for col_idx, name in columns:
            shop_cell = _cell(row, col_idx)
            if not shop_cell:
                continue
            shop_key = normalize_shop_key(shop_cell)
            if shop_key:
                shop_keys_by_name[name].add(shop_key)

    categories = [
        {
            "name": name,
            "column": chr(ord("A") + col_idx),
            "shop_keys": sorted(shop_keys_by_name[name]),
            "shop_count": len(shop_keys_by_name[name]),
        }
        for col_idx, name in columns
    ]
    return CategoryRawIndex(tab=tab, categories=categories)


def _cache_is_fresh(*, now: float | None = None) -> bool:
    if _cache is None or _cache_loaded_at is None:
        return False
    ref = now if now is not None else time.time()
    return (ref - _cache_loaded_at) < CACHE_TTL_SEC


def load_category_raw_index(*, force_refresh: bool = False) -> CategoryRawIndex:
    global _cache, _cache_loaded_at

    with _lock:
        if not force_refresh and _cache_is_fresh():
            return _cache  # type: ignore[return-value]

    if not is_configured():
        raise GoogleSheetsNotConfiguredError(
            "Google Sheets is not configured for category raw."
        )

    tab = category_raw_tab_name()
    client = get_sheets_client()
    rows = client.fetch_worksheet_values(tab)
    result = parse_category_raw_rows(rows, tab=tab)
    logger.info(
        "Category raw loaded from %r: %s categories, %s shop keys",
        tab,
        len(result.categories),
        sum(c["shop_count"] for c in result.categories),
    )

    with _lock:
        _cache = result
        _cache_loaded_at = time.time()
        return result


def get_category_raw_index(*, force_refresh: bool = False) -> CategoryRawIndex:
    return load_category_raw_index(force_refresh=force_refresh)


def get_category_mapping_payload(*, force_refresh: bool = False) -> dict[str, Any]:
    """API payload for Seller Level Analysis category SOB cards."""
    try:
        if not is_configured():
            return _empty_category_mapping_payload(error="google_sheets_not_configured")
        index = get_category_raw_index(force_refresh=force_refresh)
        return {
            "tab": index.tab,
            "loaded": True,
            "error": None,
            "categories": index.categories,
            "category_count": len(index.categories),
        }
    except (GoogleSheetsNotConfiguredError, GoogleSheetsNotEnabledError) as exc:
        return _empty_category_mapping_payload(error=str(exc))
    except Exception as exc:
        logger.warning("category raw load failed: %s", exc)
        return _empty_category_mapping_payload(error=str(exc))


def _empty_category_mapping_payload(*, error: str | None = None) -> dict[str, Any]:
    return {
        "tab": category_raw_tab_name(),
        "loaded": False,
        "error": error,
        "categories": [],
        "category_count": 0,
    }


def clear_category_raw_cache() -> None:
    global _cache, _cache_loaded_at
    with _lock:
        _cache = None
        _cache_loaded_at = None
