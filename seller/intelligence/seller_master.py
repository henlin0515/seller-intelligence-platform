"""Seller master list from Google Sheet tab ``shpoee link`` (Phase 1)."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from seller.google_sheets.client import get_sheets_client, try_get_sheets_client
from seller.google_sheets.config import is_configured
from seller.google_sheets.exceptions import (
    GoogleSheetsNotConfiguredError,
    GoogleSheetsNotEnabledError,
)

logger = logging.getLogger("seller.intelligence.seller_master")

DEFAULT_SELLER_MASTER_TAB = "shpoee link"
SELLER_MASTER_CACHE_TTL_SEC = int(os.getenv("SELLER_MASTER_CACHE_TTL_SEC", "300"))

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
_cache_loaded_at: float | None = None
_last_sync_at: datetime | None = None
_lock = threading.RLock()


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _cache_is_fresh(*, now: float | None = None) -> bool:
    if _cache is None or _cache_loaded_at is None:
        return False
    ref = now if now is not None else time.time()
    return (ref - _cache_loaded_at) < SELLER_MASTER_CACHE_TTL_SEC


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
    global _cache, _cache_loaded_at, _last_sync_at

    with _lock:
        if not force_refresh and _cache_is_fresh():
            return _cache  # type: ignore[return-value]

    if not is_configured():
        raise GoogleSheetsNotConfiguredError(
            "Google Sheets is not configured. Set GOOGLE_SHEETS_ENABLED=true, "
            "GOOGLE_SHEET_MIRROR_ID, and credentials (see GOOGLE_SHEETS_SETUP.md)."
        )

    tab = seller_master_tab_name()
    client = get_sheets_client()
    rows = client.fetch_worksheet_values(tab)
    result = parse_shpoee_link_rows(rows, tab=tab)
    synced_at = datetime.now(UTC)
    logger.info(
        "Seller master loaded from tab %r: %s sellers (%s failed, %s duplicates, %s missing TikTok)",
        tab,
        result.stats.total_loaded,
        len(result.stats.failed_rows),
        len(result.stats.duplicate_shop_ids),
        len(result.stats.missing_tiktok_shop_names),
    )

    with _lock:
        _cache = result
        _cache_loaded_at = time.time()
        _last_sync_at = synced_at
        return result


def get_seller_master(*, force_refresh: bool = False) -> SellerMasterLoadResult:
    """Cached seller master list (Google Sheet, TTL refresh)."""
    return load_seller_master_from_sheet(force_refresh=force_refresh)


def get_seller_master_sync_status() -> dict[str, Any]:
    """Public sync metadata for Settings UI and diagnostics."""
    with _lock:
        cached = _cache is not None and _cache_is_fresh()
        seller_count = len(_cache.sellers) if _cache else 0
        tab = _cache.tab if _cache else seller_master_tab_name()
        last_sync_at = _last_sync_at
        loaded_at = _cache_loaded_at

    next_refresh_at = None
    if loaded_at is not None:
        next_refresh_at = _iso_utc(datetime.fromtimestamp(loaded_at + SELLER_MASTER_CACHE_TTL_SEC, tz=UTC))

    return {
        "last_sync_at": _iso_utc(last_sync_at),
        "cache_ttl_sec": SELLER_MASTER_CACHE_TTL_SEC,
        "next_refresh_at": next_refresh_at,
        "seller_count": seller_count,
        "tab": tab,
        "data_source": "google_sheet",
        "cached": cached,
    }


def clear_seller_master_cache() -> None:
    global _cache, _cache_loaded_at, _last_sync_at
    with _lock:
        _cache = None
        _cache_loaded_at = None
        _last_sync_at = None


def sheets_available_for_seller_master() -> bool:
    return is_configured() and try_get_sheets_client() is not None
