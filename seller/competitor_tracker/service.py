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
from seller.competitor_tracker.detector import (
    detect_voucher_signals,
    enrich_fetch_with_access,
    resolve_voucher_status,
)
from seller.competitor_tracker.fetcher import fetch_tiktok_page
from seller.competitor_tracker.page_analysis import public_check_reason
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
        "check_reason": None,
        "check_summary": "",
    }
    if check:
        base.update(
            {
                "voucher_status": check.get("voucher_status", "unchecked"),
                "voucher_text": check.get("voucher_text") or "",
                "last_checked_at": check.get("last_checked_at"),
                "check_reason": check.get("check_reason"),
                "check_summary": check.get("check_summary") or "",
            }
        )
    return base


def get_cached_result(shop_id: str) -> dict[str, Any] | None:
    with _lock:
        cached = _cache.get(shop_id)
        if not cached:
            return None
        return _to_api_result(cached)


def _to_api_result(stored: dict[str, Any]) -> dict[str, Any]:
    """Strip internal fields for API responses."""
    return {
        "shop_id": stored.get("shop_id"),
        "voucher_status": stored.get("voucher_status"),
        "voucher_text": stored.get("voucher_text", ""),
        "last_checked_at": stored.get("last_checked_at"),
        "check_reason": stored.get("check_reason"),
        "check_summary": stored.get("check_summary", ""),
    }


def _run_detection_pipeline(url: str) -> dict[str, Any]:
    fetch = fetch_tiktok_page(url)
    fetch = enrich_fetch_with_access(fetch)

    detection = detect_voucher_signals(
        fetch.get("page_text") or "",
        html=fetch.get("html") or "",
        dom_snippets=fetch.get("dom_snippets"),
    )
    voucher_status = resolve_voucher_status(fetch, detection)
    check_reason = public_check_reason(fetch, detection, voucher_status)

    return {
        "voucher_status": voucher_status,
        "voucher_text": detection.get("voucher_text") or "",
        "check_reason": check_reason,
        "check_summary": check_reason.get("summary") or "",
        "_internal_error": fetch.get("fetch_error"),
    }


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
        competitors.append(_public_result(row, _to_api_result(check) if check else None))

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
    logger.info("Checking TikTok vouchers for shop_id=%s (%s)", shop_id, row.get("shop_name", ""))

    checked_at = _utc_now()
    try:
        pipeline = _run_detection_pipeline(url)
        result = {
            "shop_id": shop_id,
            "voucher_status": pipeline["voucher_status"],
            "voucher_text": pipeline["voucher_text"],
            "last_checked_at": checked_at,
            "check_reason": pipeline["check_reason"],
            "check_summary": pipeline["check_summary"],
            "_internal_error": pipeline.get("_internal_error"),
        }
    except Exception as exc:
        logger.exception("Voucher check failed for %s", shop_id)
        result = {
            "shop_id": shop_id,
            "voucher_status": "unable_to_check",
            "voucher_text": "",
            "last_checked_at": checked_at,
            "check_reason": {
                "final_url": url,
                "http_status": None,
                "page_title": "",
                "html_loaded": False,
                "html_length": 0,
                "visible_text_length": 0,
                "tiktok_blocked": False,
                "login_required": False,
                "voucher_keywords_found": False,
                "matched_keywords": [],
                "dom_voucher_found": False,
                "dom_matches": [],
                "used_playwright": False,
                "used_http": False,
                "redirect_chain": [url] if url else [],
                "fetch_error": "check_exception",
                "summary": f"Check failed safely · Result: unable to check ({type(exc).__name__})",
            },
            "check_summary": "Check failed safely · Result: unable to check",
            "_internal_error": type(exc).__name__,
        }

    with _lock:
        _cache[shop_id] = result

    return _to_api_result(result)


def check_tiktok_vouchers_for_all(
    *,
    shop_ids: list[str] | None = None,
    delay_sec: float | None = None,
    max_shops: int | None = None,
) -> dict[str, Any]:
    """
    Check TikTok voucher visibility for competitors.

    Callable from API, future cron, or external trigger.
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
        results.append(check_tiktok_shop(row))
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


def find_competitor_by_name(name_substring: str) -> list[dict[str, str]]:
    """Find sheet rows whose shop name contains substring (case-insensitive)."""
    rows, _ = _load_competitors()
    q = (name_substring or "").strip().lower()
    if not q:
        return []
    return [r for r in rows if q in (r.get("shop_name") or "").lower()]


def clear_competitor_sheet_cache() -> None:
    global _competitors_cache, _competitors_loaded_at
    with _lock:
        _competitors_cache = None
        _competitors_loaded_at = None
