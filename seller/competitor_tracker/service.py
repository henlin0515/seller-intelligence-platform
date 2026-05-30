from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

from seller.competitor_tracker.constants import (
    DEFAULT_DELAY_SEC,
    MAX_SHOPS_PER_RUN,
)
from seller.competitor_tracker.detector import detect_voucher_signals
from seller.competitor_tracker.fetcher import fetch_tiktok_page
from seller.competitor_tracker.sheet import load_competitors_from_sheet

logger = logging.getLogger("seller.competitor_tracker")

_lock = threading.Lock()
_cache: dict[str, dict[str, Any]] = {}
_competitors_cache: tuple[list[dict[str, str]], dict[str, Any]] | None = None
_competitors_loaded_at: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_result(row: dict[str, str], check: dict[str, Any] | None = None) -> dict[str, Any]:
    base = {
        "shop_id": row["shop_id"],
        "shop_name": row["shop_name"],
        "shopee_link": row.get("shopee_link", ""),
        "tiktok_link": row["tiktok_link"],
        "voucher_status": "unchecked",
        "voucher_text": "",
        "last_checked_at": None,
    }
    if check:
        base.update(
            {
                "voucher_status": check.get("voucher_status", "unchecked"),
                "voucher_text": check.get("voucher_text") or "",
                "last_checked_at": check.get("last_checked_at"),
            }
        )
    return base


def get_cached_result(shop_id: str) -> dict[str, Any] | None:
    with _lock:
        return _cache.get(shop_id)


def _load_competitors(force: bool = False) -> tuple[list[dict[str, str]], dict[str, Any]]:
    global _competitors_cache, _competitors_loaded_at
    with _lock:
        if not force and _competitors_cache is not None:
            rows, meta = _competitors_cache
            return list(rows), dict(meta)

    rows, meta = load_competitors_from_sheet()
    with _lock:
        _competitors_cache = (rows, meta)
        _competitors_loaded_at = _utc_now()
    return rows, meta


def get_competitor_list_payload(*, refresh_sheet: bool = False) -> dict[str, Any]:
    rows, meta = _load_competitors(force=refresh_sheet)
    with _lock:
        cached = dict(_cache)
    competitors = []
    for row in rows:
        check = cached.get(row["shop_id"])
        competitors.append(_public_result(row, check))

    return {
        "competitors": competitors,
        "meta": {
            **meta,
            "loaded_at": _competitors_loaded_at,
            "max_per_run": MAX_SHOPS_PER_RUN,
            "delay_sec": DEFAULT_DELAY_SEC,
        },
    }


def check_tiktok_shop(row: dict[str, str]) -> dict[str, Any]:
    """Check one competitor TikTok shop; updates in-memory cache."""
    shop_id = row["shop_id"]
    url = row.get("tiktok_link", "")
    logger.info("Checking TikTok vouchers for shop_id=%s", shop_id)

    fetch = fetch_tiktok_page(url)
    checked_at = _utc_now()

    if not fetch.get("ok"):
        result = {
            "shop_id": shop_id,
            "voucher_status": "unable_to_check",
            "voucher_text": "",
            "last_checked_at": checked_at,
            "_internal_error": fetch.get("error"),
        }
    else:
        detection = detect_voucher_signals(fetch["page_text"])
        result = {
            "shop_id": shop_id,
            "voucher_status": detection["voucher_status"],
            "voucher_text": detection.get("voucher_text") or "",
            "last_checked_at": checked_at,
            "_internal_error": None,
            "_method": fetch.get("method"),
        }

    with _lock:
        _cache[shop_id] = result

    return {
        "shop_id": shop_id,
        "voucher_status": result["voucher_status"],
        "voucher_text": result["voucher_text"],
        "last_checked_at": result["last_checked_at"],
    }


def check_tiktok_vouchers_for_all(
    *,
    shop_ids: list[str] | None = None,
    delay_sec: float | None = None,
    max_shops: int | None = None,
) -> dict[str, Any]:
    """
    Check TikTok voucher visibility for competitors.

    Callable from API, future cron, or external trigger.
    Limits shops per run and adds delay between requests.
    """
    delay = delay_sec if delay_sec is not None else DEFAULT_DELAY_SEC
    limit = min(max_shops or MAX_SHOPS_PER_RUN, MAX_SHOPS_PER_RUN)

    rows, meta = _load_competitors()
    if meta.get("error") and not rows:
        return {
            "ok": False,
            "checked": 0,
            "results": [],
            "meta": meta,
            "message": meta.get("error"),
        }

    if shop_ids:
        id_set = {str(s).strip() for s in shop_ids if str(s).strip()}
        targets = [r for r in rows if r["shop_id"] in id_set]
    else:
        targets = list(rows)

    targets = targets[:limit]
    results: list[dict[str, Any]] = []

    for i, row in enumerate(targets):
        try:
            results.append(check_tiktok_shop(row))
        except Exception as exc:
            logger.exception("Voucher check failed for %s", row.get("shop_id"))
            checked_at = _utc_now()
            fallback = {
                "shop_id": row["shop_id"],
                "voucher_status": "unable_to_check",
                "voucher_text": "",
                "last_checked_at": checked_at,
            }
            with _lock:
                _cache[row["shop_id"]] = {**fallback, "_internal_error": str(exc)}
            results.append(fallback)

        if i < len(targets) - 1 and delay > 0:
            time.sleep(delay)

    return {
        "ok": True,
        "checked": len(results),
        "results": results,
        "meta": {
            **meta,
            "limited_to": limit,
            "delay_sec": delay,
        },
    }


def clear_competitor_sheet_cache() -> None:
    """Force reload of sheet rows on next list request."""
    global _competitors_cache, _competitors_loaded_at
    with _lock:
        _competitors_cache = None
        _competitors_loaded_at = None
