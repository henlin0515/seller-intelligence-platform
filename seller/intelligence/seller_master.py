"""Seller master list from Google Sheet tab ``shpoee link`` (Phase 1)."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from seller.google_sheets.client import get_sheets_client, try_get_sheets_client
from seller.google_sheets.config import is_configured
from seller.google_sheets.exceptions import (
    GoogleSheetsNotConfiguredError,
    GoogleSheetsNotEnabledError,
)

logger = logging.getLogger("seller.intelligence.seller_master")

DEFAULT_SELLER_MASTER_TAB = "shpoee link"

_HEADER_SHOP_ID = re.compile(r"^shop\s*id$", re.I)


@dataclass(frozen=True)
class SellerMasterRecord:
    shop_id: str
    shop_name: str
    shopee_link: str
    tiktok_shop_name: str

    def as_dict(self) -> dict[str, str]:
        return {
            "shop_id": self.shop_id,
            "shop_name": self.shop_name,
            "shopee_link": self.shopee_link,
            "tiktok_shop_name": self.tiktok_shop_name,
        }


@dataclass
class SellerMasterImportStats:
    total_rows_read: int = 0
    total_loaded: int = 0
    failed_rows: list[dict[str, Any]] = field(default_factory=list)
    duplicate_shop_ids: list[str] = field(default_factory=list)
    missing_tiktok_shop_names: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_rows_read": self.total_rows_read,
            "total_loaded": self.total_loaded,
            "failed_rows": self.failed_rows,
            "failed_row_count": len(self.failed_rows),
            "duplicate_shop_ids": self.duplicate_shop_ids,
            "duplicate_shop_id_count": len(self.duplicate_shop_ids),
            "missing_tiktok_shop_names": self.missing_tiktok_shop_names,
            "missing_tiktok_shop_name_count": len(self.missing_tiktok_shop_names),
        }


@dataclass
class SellerMasterLoadResult:
    sellers: list[SellerMasterRecord]
    stats: SellerMasterImportStats
    tab: str
    data_source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "tab": self.tab,
            "data_source": self.data_source,
            "sellers": [s.as_dict() for s in self.sellers],
            "import": self.stats.as_dict(),
        }


_cache: SellerMasterLoadResult | None = None


def seller_master_tab_name() -> str:
    return (os.getenv("GOOGLE_SHEET_SELLER_MASTER_TAB") or DEFAULT_SELLER_MASTER_TAB).strip()


def _cell(row: list[Any], index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _is_header_row(row: list[Any]) -> bool:
    first = _cell(row, 0)
    return bool(first and _HEADER_SHOP_ID.match(first))


def parse_shpoee_link_rows(
    rows: list[list[Any]],
    *,
    tab: str = DEFAULT_SELLER_MASTER_TAB,
) -> SellerMasterLoadResult:
    """
    Parse grid from tab ``shpoee link``.

    Columns: A=Shop ID, B=Shop Name, C=Shopee Link, D=TikTok Shop Name.
    """
    stats = SellerMasterImportStats()
    sellers: list[SellerMasterRecord] = []
    seen_ids: dict[str, int] = {}

    start = 1 if rows and _is_header_row(rows[0]) else 0
    for row_index, row in enumerate(rows[start:], start=start + 1):
        stats.total_rows_read += 1
        shop_id = _cell(row, 0)
        shop_name = _cell(row, 1)
        shopee_link = _cell(row, 2)
        tiktok_shop_name = _cell(row, 3)

        if not shop_id and not shop_name and not shopee_link and not tiktok_shop_name:
            stats.failed_rows.append(
                {"row": row_index, "reason": "empty_row", "shop_id": shop_id}
            )
            continue

        if not shop_id:
            stats.failed_rows.append(
                {"row": row_index, "reason": "missing_shop_id", "shop_name": shop_name}
            )
            continue

        if shop_id in seen_ids:
            if shop_id not in stats.duplicate_shop_ids:
                stats.duplicate_shop_ids.append(shop_id)
            stats.failed_rows.append(
                {
                    "row": row_index,
                    "reason": "duplicate_shop_id",
                    "shop_id": shop_id,
                    "first_seen_row": seen_ids[shop_id],
                }
            )
            continue

        seen_ids[shop_id] = row_index
        if not shop_name:
            stats.failed_rows.append(
                {"row": row_index, "reason": "missing_shop_name", "shop_id": shop_id}
            )
            continue

        if not tiktok_shop_name:
            stats.missing_tiktok_shop_names.append(shop_id)

        sellers.append(
            SellerMasterRecord(
                shop_id=shop_id,
                shop_name=shop_name,
                shopee_link=shopee_link,
                tiktok_shop_name=tiktok_shop_name,
            )
        )

    stats.total_loaded = len(sellers)
    return SellerMasterLoadResult(
        sellers=sellers,
        stats=stats,
        tab=tab,
        data_source="google_sheet",
    )


def load_seller_master_from_sheet(*, force_refresh: bool = False) -> SellerMasterLoadResult:
    """Fetch seller master from Google Sheets (requires GOOGLE_SHEETS_ENABLED + credentials)."""
    global _cache
    if _cache is not None and not force_refresh:
        return _cache

    if not is_configured():
        raise GoogleSheetsNotConfiguredError(
            "Google Sheets is not configured. Set GOOGLE_SHEETS_ENABLED=true, "
            "GOOGLE_SHEET_MIRROR_ID, and credentials (see GOOGLE_SHEETS_SETUP.md)."
        )

    tab = seller_master_tab_name()
    client = get_sheets_client()
    rows = client.fetch_worksheet_values(tab)
    result = parse_shpoee_link_rows(rows, tab=tab)
    logger.info(
        "Seller master loaded from tab %r: %s sellers (%s failed, %s duplicates, %s missing TikTok)",
        tab,
        result.stats.total_loaded,
        len(result.stats.failed_rows),
        len(result.stats.duplicate_shop_ids),
        len(result.stats.missing_tiktok_shop_names),
    )
    _cache = result
    return result


def get_seller_master(*, force_refresh: bool = False) -> SellerMasterLoadResult:
    """Cached seller master list (Google Sheet)."""
    return load_seller_master_from_sheet(force_refresh=force_refresh)


def clear_seller_master_cache() -> None:
    global _cache
    _cache = None


def sheets_available_for_seller_master() -> bool:
    return is_configured() and try_get_sheets_client() is not None
