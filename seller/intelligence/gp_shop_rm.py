"""RM / GP / shop mapping from Google Sheet tab ``GP SHOP AND RM RAW``."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from seller.google_sheets.client import get_sheets_client, try_get_sheets_client
from seller.google_sheets.config import is_configured
from seller.google_sheets.exceptions import (
    GoogleSheetsNotConfiguredError,
    GoogleSheetsNotEnabledError,
)

logger = logging.getLogger("seller.intelligence.gp_shop_rm")

DEFAULT_GP_SHOP_RM_TAB = "GP SHOP AND RM RAW"
ALL_RM_VALUE = "all"

_HEADER_RM = re.compile(r"^rm$", re.I)
_HEADER_GP = re.compile(r"^gp\s*name$", re.I)
_HEADER_SHOP = re.compile(r"^shop\s*name$", re.I)

_cache: "GpShopRmIndex | None" = None
_cache_loaded_at: float | None = None
_lock = threading.RLock()
CACHE_TTL_SEC = int(os.getenv("GP_SHOP_RM_CACHE_TTL_SEC", "300"))


def gp_shop_rm_tab_name() -> str:
    return (os.getenv("GOOGLE_SHEET_GP_SHOP_RM_TAB") or DEFAULT_GP_SHOP_RM_TAB).strip()


def normalize_shop_key(value: str) -> str:
    """Case-insensitive shop key with trimmed, collapsed whitespace."""
    return " ".join((value or "").strip().lower().split())


def _cell(row: list[Any], index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _is_header_row(row: list[Any]) -> bool:
    a = _cell(row, 0)
    b = _cell(row, 1)
    c = _cell(row, 2)
    return bool(
        (_HEADER_RM.match(a) and _HEADER_GP.match(b) and _HEADER_SHOP.match(c))
        or (a.lower() == "rm" and "gp" in b.lower() and "shop" in c.lower())
    )


@dataclass
class GpShopRmIndex:
    tab: str
    by_rm: dict[str, set[str]] = field(default_factory=dict)
    all_keys: set[str] = field(default_factory=set)

    @property
    def rm_options(self) -> list[str]:
        return sorted(self.by_rm.keys(), key=lambda x: x.lower())

    def as_filter_payload(self) -> dict[str, Any]:
        return {
            "tab": self.tab,
            "default": ALL_RM_VALUE,
            "options": [
                {"value": ALL_RM_VALUE, "label": "All RM"},
                *[{"value": rm, "label": rm} for rm in self.rm_options],
            ],
            "by_rm": {rm: sorted(names) for rm, names in self.by_rm.items()},
        }


def parse_gp_shop_rm_rows(
    rows: list[list[Any]],
    *,
    tab: str = DEFAULT_GP_SHOP_RM_TAB,
) -> GpShopRmIndex:
    """
    Parse grouped RM sheet: forward-fill RM (A) and GP NAME (B); collect SHOP NAME (C).
    GP names are included in each RM's match set for shop matching.
    """
    by_rm: dict[str, set[str]] = {}
    all_keys: set[str] = set()
    current_rm = ""
    current_gp = ""

    start = 1 if rows and _is_header_row(rows[0]) else 0
    for row in rows[start:]:
        rm_cell = _cell(row, 0)
        gp_cell = _cell(row, 1)
        shop_cell = _cell(row, 2)

        if rm_cell:
            current_rm = rm_cell
        if gp_cell:
            current_gp = gp_cell

        if not shop_cell:
            continue
        if not current_rm:
            continue

        bucket = by_rm.setdefault(current_rm, set())
        shop_key = normalize_shop_key(shop_cell)
        if shop_key:
            bucket.add(shop_key)
            all_keys.add(shop_key)
        if current_gp:
            gp_key = normalize_shop_key(current_gp)
            if gp_key:
                bucket.add(gp_key)
                all_keys.add(gp_key)

    return GpShopRmIndex(tab=tab, by_rm=by_rm, all_keys=all_keys)


def seller_matches_rm(
    *,
    shop_name: str,
    tiktok_shop_name: str = "",
    rm_value: str,
    index: GpShopRmIndex | None,
) -> bool:
    """Return True if seller should show for the selected RM filter."""
    if not rm_value or rm_value == ALL_RM_VALUE:
        return True
    if index is None or not index.by_rm:
        return True

    allowed = index.by_rm.get(rm_value)
    if not allowed:
        return False

    keys = [normalize_shop_key(shop_name), normalize_shop_key(tiktok_shop_name)]
    return any(k and k in allowed for k in keys)


def _cache_is_fresh(*, now: float | None = None) -> bool:
    if _cache is None or _cache_loaded_at is None:
        return False
    ref = now if now is not None else time.time()
    return (ref - _cache_loaded_at) < CACHE_TTL_SEC


def load_gp_shop_rm_index(*, force_refresh: bool = False) -> GpShopRmIndex:
    global _cache, _cache_loaded_at

    with _lock:
        if not force_refresh and _cache_is_fresh():
            return _cache  # type: ignore[return-value]

    if not is_configured():
        raise GoogleSheetsNotConfiguredError(
            "Google Sheets is not configured for GP SHOP AND RM RAW."
        )

    tab = gp_shop_rm_tab_name()
    client = get_sheets_client()
    rows = client.fetch_worksheet_values(tab)
    result = parse_gp_shop_rm_rows(rows, tab=tab)
    logger.info(
        "GP shop RM mapping loaded from %r: %s RMs, %s shop keys",
        tab,
        len(result.by_rm),
        len(result.all_keys),
    )

    with _lock:
        _cache = result
        _cache_loaded_at = time.time()
        return result


def get_gp_shop_rm_index(*, force_refresh: bool = False) -> GpShopRmIndex:
    return load_gp_shop_rm_index(force_refresh=force_refresh)


def get_rm_filter_payload(*, force_refresh: bool = False) -> dict[str, Any]:
    """API payload for Seller Level Analysis RM dropdown."""
    try:
        if not is_configured():
            return _empty_rm_filter_payload(error="google_sheets_not_configured")
        index = get_gp_shop_rm_index(force_refresh=force_refresh)
        payload = index.as_filter_payload()
        payload["loaded"] = True
        payload["rm_count"] = len(index.rm_options)
        payload["shop_key_count"] = len(index.all_keys)
        return payload
    except (GoogleSheetsNotConfiguredError, GoogleSheetsNotEnabledError) as exc:
        return _empty_rm_filter_payload(error=str(exc))
    except Exception as exc:
        logger.warning("GP SHOP AND RM RAW load failed: %s", exc)
        return _empty_rm_filter_payload(error=str(exc))


def _empty_rm_filter_payload(*, error: str | None = None) -> dict[str, Any]:
    return {
        "tab": gp_shop_rm_tab_name(),
        "default": ALL_RM_VALUE,
        "loaded": False,
        "error": error,
        "options": [{"value": ALL_RM_VALUE, "label": "All RM"}],
        "by_rm": {},
        "rm_count": 0,
        "shop_key_count": 0,
    }


def clear_gp_shop_rm_cache() -> None:
    global _cache, _cache_loaded_at
    with _lock:
        _cache = None
        _cache_loaded_at = None


def try_get_gp_shop_rm_index() -> GpShopRmIndex | None:
    if not is_configured():
        return None
    client = try_get_sheets_client()
    if client is None:
        return None
    try:
        return get_gp_shop_rm_index()
    except Exception:
        return None
