"""Shopee ADGMV from Google Sheet tab ``shopee adgmv raw data`` (Tracker)."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from seller.google_sheets.client import get_sheets_client
from seller.google_sheets.config import is_configured
from seller.google_sheets.exceptions import (
    GoogleSheetsNotConfiguredError,
    GoogleSheetsNotEnabledError,
)

logger = logging.getLogger("seller.intelligence.business.shopee_adgmv")

DEFAULT_SHOPEE_ADGMV_TAB = "shopee adgmv raw data"

_HEADER_SHOP_NAME = re.compile(r"^shop[_\s-]*name$", re.I)
_HEADER_MTD = re.compile(r"^mtd_adgmv_usd$", re.I)
_HEADER_M1 = re.compile(r"^m[_\s-]*1_adgmv_usd$", re.I)


@dataclass(frozen=True)
class ShopeeAdgmvRecord:
    tracker_shop_name: str
    mtd_adgmv_usd: float
    m1_adgmv_usd: float


@dataclass
class ShopeeAdgmvImportStats:
    total_rows_read: int = 0
    total_loaded: int = 0
    duplicate_shop_names: list[str] = field(default_factory=list)
    skipped_rows: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_rows_read": self.total_rows_read,
            "total_loaded": self.total_loaded,
            "duplicate_shop_name_count": len(self.duplicate_shop_names),
            "duplicate_shop_names": self.duplicate_shop_names,
            "skipped_row_count": len(self.skipped_rows),
            "skipped_rows": self.skipped_rows,
        }


@dataclass
class ShopeeAdgmvLoadResult:
    by_shop_name: dict[str, ShopeeAdgmvRecord]
    stats: ShopeeAdgmvImportStats
    tab: str
    data_source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "tab": self.tab,
            "data_source": self.data_source,
            "import": self.stats.as_dict(),
            "loaded_count": len(self.by_shop_name),
        }


_cache: ShopeeAdgmvLoadResult | None = None


def shopee_adgmv_tab_name() -> str:
    return (os.getenv("GOOGLE_SHEET_SHOPEE_ADGMV_TAB") or DEFAULT_SHOPEE_ADGMV_TAB).strip()


def normalize_shop_name(name: str) -> str:
    """Trim + case-insensitive key for exact shop name matching."""
    return (name or "").strip().casefold()


def _cell(row: list[Any], index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _parse_float(value: str) -> float:
    text = (value or "").strip().replace(",", "")
    if not text:
        return 0.0
    return float(text)


def _header_indexes(header_row: list[Any]) -> dict[str, int]:
    indexes: dict[str, int] = {}
    for index, cell in enumerate(header_row):
        label = _cell([cell], 0).lower()
        if _HEADER_SHOP_NAME.match(label):
            indexes["shop_name"] = index
        elif _HEADER_MTD.match(label):
            indexes["mtd_adgmv_usd"] = index
        elif _HEADER_M1.match(label):
            indexes["m_1_adgmv_usd"] = index
    missing = [key for key in ("shop_name", "mtd_adgmv_usd", "m_1_adgmv_usd") if key not in indexes]
    if missing:
        raise ValueError(f"Missing required columns in Shopee ADGMV tab: {', '.join(missing)}")
    return indexes


def parse_shopee_adgmv_rows(
    rows: list[list[Any]],
    *,
    tab: str = DEFAULT_SHOPEE_ADGMV_TAB,
) -> ShopeeAdgmvLoadResult:
    """Parse Tracker grid: shop_name, mtd_adgmv_usd, m_1_adgmv_usd."""
    stats = ShopeeAdgmvImportStats()
    by_name: dict[str, ShopeeAdgmvRecord] = {}

    if not rows:
        return ShopeeAdgmvLoadResult(by_name, stats, tab=tab, data_source="google_sheet")

    indexes = _header_indexes(rows[0])
    for row_index, row in enumerate(rows[1:], start=2):
        stats.total_rows_read += 1
        shop_name = _cell(row, indexes["shop_name"])
        if not shop_name:
            stats.skipped_rows.append({"row": row_index, "reason": "missing_shop_name"})
            continue

        key = normalize_shop_name(shop_name)
        if key in by_name:
            if shop_name not in stats.duplicate_shop_names:
                stats.duplicate_shop_names.append(shop_name)
            stats.skipped_rows.append(
                {"row": row_index, "reason": "duplicate_shop_name", "shop_name": shop_name}
            )
            continue

        try:
            record = ShopeeAdgmvRecord(
                tracker_shop_name=shop_name.strip(),
                mtd_adgmv_usd=_parse_float(_cell(row, indexes["mtd_adgmv_usd"])),
                m1_adgmv_usd=_parse_float(_cell(row, indexes["m_1_adgmv_usd"])),
            )
        except ValueError as exc:
            stats.skipped_rows.append(
                {
                    "row": row_index,
                    "reason": "invalid_numeric_value",
                    "shop_name": shop_name,
                    "error": str(exc),
                }
            )
            continue

        by_name[key] = record

    stats.total_loaded = len(by_name)
    return ShopeeAdgmvLoadResult(
        by_shop_name=by_name,
        stats=stats,
        tab=tab,
        data_source="google_sheet",
    )


def load_shopee_adgmv_from_sheet(*, force_refresh: bool = False) -> ShopeeAdgmvLoadResult:
    global _cache
    if _cache is not None and not force_refresh:
        return _cache

    if not is_configured():
        raise GoogleSheetsNotConfiguredError(
            "Google Sheets is not configured for Shopee ADGMV import."
        )

    tab = shopee_adgmv_tab_name()
    client = get_sheets_client()
    rows = client.fetch_worksheet_values(tab)
    result = parse_shopee_adgmv_rows(rows, tab=tab)
    logger.info(
        "Shopee ADGMV loaded from tab %r: %s shops (%s tracker rows read, %s duplicates)",
        tab,
        result.stats.total_loaded,
        result.stats.total_rows_read,
        len(result.stats.duplicate_shop_names),
    )
    _cache = result
    return result


def get_shopee_adgmv(*, force_refresh: bool = False) -> ShopeeAdgmvLoadResult:
    return load_shopee_adgmv_from_sheet(force_refresh=force_refresh)


def clear_shopee_adgmv_cache() -> None:
    global _cache
    _cache = None


def match_shopee_adgmv_to_shop_name(
    shop_name: str,
    tracker: ShopeeAdgmvLoadResult,
) -> ShopeeAdgmvRecord | None:
    """Exact match on trimmed, case-insensitive shop name."""
    return tracker.by_shop_name.get(normalize_shop_name(shop_name))
