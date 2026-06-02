"""
In-memory cache of merged mirror sheet data (Shop ID primary key).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from seller.google_sheets.client import get_sheets_client
from seller.google_sheets.config import (
    get_credentials_source,
    get_settings,
    is_configured,
    log_startup_configuration,
    validate_for_connection,
)
from seller.google_sheets.merge import merge_tabs, should_skip_tab

logger = logging.getLogger("seller.sheets_cache")

_lock = threading.RLock()
_state: dict[str, Any] = {
    "loaded": False,
    "loading": False,
    "error": None,
    "sellers": {},
    "last_loaded_at": None,
    "load_summary": None,
    "spreadsheet_title": None,
    "column_schema": [],
}


def _use_live_sheets() -> bool:
    return is_configured()


def is_loaded() -> bool:
    with _lock:
        return bool(_state["loaded"] and _state["sellers"])


def is_loading() -> bool:
    with _lock:
        return bool(_state["loading"])


def get_load_error() -> str | None:
    with _lock:
        return _state.get("error")


def get_seller_count() -> int:
    with _lock:
        return len(_state["sellers"]) if _state["loaded"] else 0


def get_load_summary() -> dict[str, Any] | None:
    with _lock:
        return _state.get("load_summary")


def get_column_schema() -> list[dict[str, Any]]:
    with _lock:
        return list(_state.get("column_schema") or [])


def get_status() -> dict[str, Any]:
    settings = get_settings()
    with _lock:
        summary = _state.get("load_summary") or {}
        return {
            "live_sheets_configured": _use_live_sheets(),
            "loaded": _state["loaded"],
            "loading": _state["loading"],
            "seller_count": len(_state["sellers"]) if _state["loaded"] else 0,
            "last_loaded_at": _state.get("last_loaded_at"),
            "error": _state.get("error"),
            "spreadsheet_id": settings.spreadsheet_id if _use_live_sheets() else None,
            "spreadsheet_title": _state.get("spreadsheet_title"),
            "data_source": "google_sheets" if _state["loaded"] else ("mock" if not _use_live_sheets() else "pending"),
            "tabs_discovered": summary.get("tabs_discovered"),
            "tabs_merged": summary.get("tabs_merged"),
            "tabs_skipped": summary.get("tabs_skipped"),
            "tab_structures": summary.get("tab_structures"),
            "shop_id_field": summary.get("shop_id_field"),
            "primary_tab": summary.get("primary_tab"),
            "total_grid_rows_read": summary.get("total_grid_rows_read"),
            "total_columns_merged": summary.get("total_columns_merged"),
            "total_columns_loaded": summary.get("total_columns_loaded"),
            "total_seller_rows_loaded": summary.get("total_seller_rows_loaded"),
            "layout": summary.get("layout"),
            "merge_strategy": summary.get("merge_strategy"),
        }


def get_public_status() -> dict[str, Any]:
    """Minimal status for authenticated UI — no sheet IDs, sources, or diagnostics."""
    full = get_status()
    return {
        "loaded": bool(full.get("loaded")),
        "loading": bool(full.get("loading")),
        "seller_count": int(full.get("seller_count") or 0),
        "last_loaded_at": full.get("last_loaded_at"),
    }


def refresh(*, force: bool = False) -> dict[str, Any]:
    """
    Load or reload all mirror tabs into memory.
    Returns status dict after load completes.
    """
    if not _use_live_sheets():
        settings = get_settings()
        issues = validate_for_connection()
        detail = "; ".join(issues) if issues else "unknown configuration problem"
        log_startup_configuration()
        raise RuntimeError(
            "Google Sheets is not configured. "
            f"GOOGLE_SHEETS_ENABLED={settings.enabled!r}, "
            f"spreadsheet_id_set={settings.has_spreadsheet_id}, "
            f"credentials_source={get_credentials_source()}. "
            f"Details: {detail}"
        )

    with _lock:
        if _state["loading"]:
            return get_status()
        _state["loading"] = True
        _state["error"] = None

    try:
        settings = get_settings()
        client = get_sheets_client()
        ping = client.ping()
        titles = ping["worksheet_titles"]
        tab_grids: dict[str, list[list[Any]]] = {}
        for title in titles:
            if should_skip_tab(title):
                tab_grids[title] = []
                continue
            tab_grids[title] = client.fetch_worksheet_values(title)

        sellers, summary = merge_tabs(
            tab_grids,
            primary_tab_hint=settings.primary_tab_hint,
        )
        summary["spreadsheet_title"] = ping.get("spreadsheet_title")
        summary["spreadsheet_id"] = ping.get("spreadsheet_id")
        summary["service_account_email"] = ping.get("service_account_email")

        layout = summary.get("layout") or {}
        with _lock:
            _state["sellers"] = sellers
            _state["loaded"] = True
            _state["loading"] = False
            _state["load_summary"] = summary
            _state["spreadsheet_title"] = ping.get("spreadsheet_title")
            _state["column_schema"] = layout.get("column_schema") or []
            _state["last_loaded_at"] = datetime.now(timezone.utc).isoformat()
            _state["error"] = None

        logger.info("Sheet cache refreshed: %s sellers", len(sellers))
        return get_status()
    except Exception as exc:
        logger.exception("Failed to refresh sheet cache")
        with _lock:
            _state["loading"] = False
            _state["error"] = str(exc)
            if force:
                _state["loaded"] = False
        raise


def ensure_loaded() -> None:
    if not _use_live_sheets():
        return
    if not is_loaded() and not is_loading():
        refresh()


def lookup_shop(shop_id_or_name: str) -> dict[str, Any] | None:
    """Match Shop ID first, then Shop Name (column K)."""
    query = shop_id_or_name.strip()
    if not query:
        return None
    with _lock:
        sellers = _state["sellers"]
        if query in sellers:
            return sellers[query]
        lower = query.lower()
        for key, entry in sellers.items():
            if key.lower() == lower:
                return entry
        for entry in sellers.values():
            name = (entry.get("shop_name") or "").strip()
            if name.lower() == lower:
                return entry
        for entry in sellers.values():
            name = (entry.get("shop_name") or "").strip()
            if lower in name.lower():
                return entry
    return None


def search_shops(query: str) -> list[dict[str, str]]:
    q = query.strip().lower()
    if not q:
        return []
    with _lock:
        sellers = list(_state["sellers"].values())
    out = []
    for entry in sellers:
        sid = entry.get("shop_id", "")
        name = entry.get("shop_name", "")
        if q in sid.lower() or q in name.lower():
            out.append(
                {
                    "shop_id": sid,
                    "shop_name": name,
                    "tier": entry.get("tier", ""),
                    "category": entry.get("category", ""),
                }
            )
    return out[:50]


def entry_to_raw_row(entry: dict[str, Any]) -> dict[str, Any]:
    """Shape expected by seller.service / metric_resolver."""
    return {
        "shop_id": entry["shop_id"],
        "shop_name": entry.get("shop_name") or entry["shop_id"],
        "tier": entry.get("tier", ""),
        "category": entry.get("category", ""),
        "raw": entry.get("raw", {}),
    }
