"""Extra Seller Level Analysis shops from ``shopee shop only`` and ``tiktok shop only`` tabs."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from seller.google_sheets.client import get_sheets_client, try_get_sheets_client
from seller.google_sheets.config import is_configured
from seller.google_sheets.exceptions import (
    GoogleSheetsNotConfiguredError,
    GoogleSheetsNotEnabledError,
)
from seller.intelligence.gp_shop_rm import normalize_shop_key

logger = logging.getLogger("seller.intelligence.platform_extra_shops")

DEFAULT_SHOPEE_SHOP_ONLY_TAB = "shopee shop only"
DEFAULT_TIKTOK_SHOP_ONLY_TAB = "tiktok shop only"

PlatformSource = Literal["NORMAL", "SHOPEE_ONLY", "TIKTOK_ONLY"]

_HEADER_GP_SHOP_ID = re.compile(r"^gp\s*shop\s*id$", re.I)
_HEADER_GP_SHOP_NAME = re.compile(r"^gp\s*shop\s*name$", re.I)
_HEADER_SHOP_ID = re.compile(r"^shop\s*id$", re.I)
_HEADER_SHOPEE_SHOP = re.compile(r"^shopee\s*shop\s*name$", re.I)
_HEADER_TIKTOK_SHOP = re.compile(r"^tiktok\s*shop\s*name$", re.I)
_HEADER_RM = re.compile(r"^rm$", re.I)

_cache_lock = threading.RLock()
_shopee_cache: "ShopeeShopOnlyLoadResult | None" = None
_shopee_loaded_at: float | None = None
_tiktok_cache: "TiktokShopOnlyLoadResult | None" = None
_tiktok_loaded_at: float | None = None
CACHE_TTL_SEC = int(os.getenv("PLATFORM_EXTRA_SHOPS_CACHE_TTL_SEC", "300"))


@dataclass(frozen=True)
class ShopeeShopOnlyRecord:
    gp_shop_id: str
    gp_shop_name: str
    shop_id: str
    shop_name: str
    rm: str

    @property
    def platform_source(self) -> PlatformSource:
        return "SHOPEE_ONLY"


@dataclass(frozen=True)
class TiktokShopOnlyRecord:
    gp_shop_id: str
    gp_shop_name: str
    tiktok_shop_name: str

    @property
    def platform_source(self) -> PlatformSource:
        return "TIKTOK_ONLY"

    @property
    def synthetic_shop_id(self) -> str:
        key = normalize_shop_key(self.tiktok_shop_name) or normalize_shop_key(self.gp_shop_id)
        return f"tkonly:{key or 'unknown'}"


@dataclass
class ShopeeShopOnlyLoadResult:
    rows: list[ShopeeShopOnlyRecord]
    tab: str
    data_source: str
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class TiktokShopOnlyLoadResult:
    rows: list[TiktokShopOnlyRecord]
    tab: str
    data_source: str
    stats: dict[str, Any] = field(default_factory=dict)


def shopee_shop_only_tab_name() -> str:
    return (os.getenv("GOOGLE_SHEET_SHOPEE_SHOP_ONLY_TAB") or DEFAULT_SHOPEE_SHOP_ONLY_TAB).strip()


def tiktok_shop_only_tab_name() -> str:
    return (os.getenv("GOOGLE_SHEET_TIKTOK_SHOP_ONLY_TAB") or DEFAULT_TIKTOK_SHOP_ONLY_TAB).strip()


def _cell(row: list[Any], index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _is_shopee_only_header(row: list[Any]) -> bool:
    a, b, c, d = (_cell(row, i) for i in range(4))
    return bool(
        _HEADER_GP_SHOP_ID.match(a)
        and _HEADER_GP_SHOP_NAME.match(b)
        and _HEADER_SHOP_ID.match(c)
        and _HEADER_SHOPEE_SHOP.match(d)
    )


def _is_tiktok_only_header(row: list[Any]) -> bool:
    a, b, c = (_cell(row, i) for i in range(3))
    return bool(
        _HEADER_GP_SHOP_ID.match(a)
        and _HEADER_GP_SHOP_NAME.match(b)
        and _HEADER_TIKTOK_SHOP.match(c)
    )


def parse_shopee_shop_only_rows(
    rows: list[list[Any]],
    *,
    tab: str = DEFAULT_SHOPEE_SHOP_ONLY_TAB,
) -> ShopeeShopOnlyLoadResult:
    out: list[ShopeeShopOnlyRecord] = []
    skipped = 0
    start = 0
    if rows and _is_shopee_only_header(rows[0]):
        start = 1

    for row_index, row in enumerate(rows[start:], start=start + 1):
        gp_shop_id = _cell(row, 0)
        gp_shop_name = _cell(row, 1)
        shop_id = _cell(row, 2)
        shop_name = _cell(row, 3)
        rm = _cell(row, 4)
        if not shop_id and not shop_name:
            continue
        if not shop_id:
            skipped += 1
            continue
        out.append(
            ShopeeShopOnlyRecord(
                gp_shop_id=gp_shop_id,
                gp_shop_name=gp_shop_name,
                shop_id=shop_id,
                shop_name=shop_name or shop_id,
                rm=rm,
            )
        )

    return ShopeeShopOnlyLoadResult(
        rows=out,
        tab=tab,
        data_source="google_sheet",
        stats={"total_rows_read": len(rows), "total_loaded": len(out), "skipped_missing_shop_id": skipped},
    )


def parse_tiktok_shop_only_rows(
    rows: list[list[Any]],
    *,
    tab: str = DEFAULT_TIKTOK_SHOP_ONLY_TAB,
) -> TiktokShopOnlyLoadResult:
    out: list[TiktokShopOnlyRecord] = []
    start = 0
    if rows and _is_tiktok_only_header(rows[0]):
        start = 1

    for row in rows[start:]:
        gp_shop_id = _cell(row, 0)
        gp_shop_name = _cell(row, 1)
        tiktok_shop_name = _cell(row, 2)
        if not tiktok_shop_name and not gp_shop_name:
            continue
        if not tiktok_shop_name:
            continue
        out.append(
            TiktokShopOnlyRecord(
                gp_shop_id=gp_shop_id,
                gp_shop_name=gp_shop_name,
                tiktok_shop_name=tiktok_shop_name,
            )
        )

    return TiktokShopOnlyLoadResult(
        rows=out,
        tab=tab,
        data_source="google_sheet",
        stats={"total_rows_read": len(rows), "total_loaded": len(out)},
    )


def _cache_fresh(loaded_at: float | None) -> bool:
    if loaded_at is None:
        return False
    return (time.time() - loaded_at) < CACHE_TTL_SEC


def load_shopee_shop_only(*, force_refresh: bool = False) -> ShopeeShopOnlyLoadResult:
    global _shopee_cache, _shopee_loaded_at
    with _cache_lock:
        if not force_refresh and _cache_fresh(_shopee_loaded_at) and _shopee_cache is not None:
            return _shopee_cache

    if not is_configured():
        return ShopeeShopOnlyLoadResult(
            rows=[],
            tab=shopee_shop_only_tab_name(),
            data_source="unavailable",
            stats={"error": "google_sheets_not_configured"},
        )

    tab = shopee_shop_only_tab_name()
    try:
        client = get_sheets_client()
        rows = client.fetch_worksheet_values(tab)
        result = parse_shopee_shop_only_rows(rows, tab=tab)
        logger.info("Shopee shop only loaded from %r: %s rows", tab, len(result.rows))
        _shopee_cache = result
        _shopee_loaded_at = time.time()
        return result
    except (GoogleSheetsNotConfiguredError, GoogleSheetsNotEnabledError) as exc:
        return ShopeeShopOnlyLoadResult(
            rows=[],
            tab=tab,
            data_source="unavailable",
            stats={"error": str(exc)},
        )
    except Exception as exc:
        logger.warning("Shopee shop only load failed: %s", exc)
        return ShopeeShopOnlyLoadResult(
            rows=[],
            tab=tab,
            data_source="unavailable",
            stats={"error": str(exc)},
        )


def load_tiktok_shop_only(*, force_refresh: bool = False) -> TiktokShopOnlyLoadResult:
    global _tiktok_cache, _tiktok_loaded_at
    with _cache_lock:
        if not force_refresh and _cache_fresh(_tiktok_loaded_at) and _tiktok_cache is not None:
            return _tiktok_cache

    if not is_configured():
        return TiktokShopOnlyLoadResult(
            rows=[],
            tab=tiktok_shop_only_tab_name(),
            data_source="unavailable",
            stats={"error": "google_sheets_not_configured"},
        )

    tab = tiktok_shop_only_tab_name()
    try:
        client = get_sheets_client()
        rows = client.fetch_worksheet_values(tab)
        result = parse_tiktok_shop_only_rows(rows, tab=tab)
        logger.info("TikTok shop only loaded from %r: %s rows", tab, len(result.rows))
        _tiktok_cache = result
        _tiktok_loaded_at = time.time()
        return result
    except (GoogleSheetsNotConfiguredError, GoogleSheetsNotEnabledError) as exc:
        return TiktokShopOnlyLoadResult(
            rows=[],
            tab=tab,
            data_source="unavailable",
            stats={"error": str(exc)},
        )
    except Exception as exc:
        logger.warning("TikTok shop only load failed: %s", exc)
        return TiktokShopOnlyLoadResult(
            rows=[],
            tab=tab,
            data_source="unavailable",
            stats={"error": str(exc)},
        )


def try_load_platform_extra_shops() -> tuple[ShopeeShopOnlyLoadResult, TiktokShopOnlyLoadResult]:
    if not is_configured() or try_get_sheets_client() is None:
        empty = ShopeeShopOnlyLoadResult(rows=[], tab=shopee_shop_only_tab_name(), data_source="unavailable")
        empty_tk = TiktokShopOnlyLoadResult(rows=[], tab=tiktok_shop_only_tab_name(), data_source="unavailable")
        return empty, empty_tk
    return load_shopee_shop_only(), load_tiktok_shop_only()


def clear_platform_extra_shops_cache() -> None:
    global _shopee_cache, _shopee_loaded_at, _tiktok_cache, _tiktok_loaded_at
    with _cache_lock:
        _shopee_cache = None
        _shopee_loaded_at = None
        _tiktok_cache = None
        _tiktok_loaded_at = None
