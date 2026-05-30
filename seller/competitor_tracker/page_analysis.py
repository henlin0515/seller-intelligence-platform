from __future__ import annotations

import re
from typing import Any

BLOCKED_MARKERS = (
    "access denied",
    "verify you are human",
    "security check",
    "captcha",
    "unusual traffic",
    "too many requests",
    "访问过于频繁",
    "请完成验证",
    "robot check",
    "enable javascript",
)

LOGIN_MARKERS = (
    "log in to continue",
    "login to view",
    "sign in to continue",
    "sign in to view",
    "请先登录",
    "登录后查看",
    "log in",
    "sign in",
)


def analyze_access_signals(
    page_text: str,
    page_title: str = "",
    http_status: int | None = None,
) -> dict[str, bool]:
    combined = f"{page_title}\n{page_text}".lower()
    blocked = False
    if http_status in (403, 429, 503):
        blocked = True
    if any(m in combined for m in BLOCKED_MARKERS):
        blocked = True
    if len(page_text) < 80 and http_status and http_status >= 400:
        blocked = True

    login_required = False
    if any(m in combined for m in LOGIN_MARKERS):
        if len(page_text) < 2500 or "log in to continue" in combined or "login to view" in combined:
            login_required = True

    return {"tiktok_blocked": blocked, "login_required": login_required}


def public_pipeline_check_reason(
    *,
    profile_url: str,
    profile: dict[str, Any],
    search: dict[str, Any],
    match: dict[str, Any] | None,
    shop_fetch: dict[str, Any],
    detection: dict[str, Any],
    voucher_status: str,
    summary: str,
) -> dict[str, Any]:
    """Diagnostics for profile -> shop search -> voucher pipeline (UI-safe)."""
    selected = ""
    if match:
        selected = f"{match.get('shop_name', '')} ({match.get('shop_url', '')})"

    voucher_detection = "not checked"
    if voucher_status == "found":
        voucher_detection = f"Found: {(detection.get('voucher_text') or '')[:120]}"
    elif voucher_status == "not_found" and match:
        voucher_detection = "No visible voucher on shop page"
    elif voucher_status == "shop_not_found":
        voucher_detection = "Shop not found — voucher check skipped"
    elif voucher_status == "unable_to_check":
        voucher_detection = "Unable to check vouchers"

    return {
        "profile_url": profile_url,
        "extracted_profile_name": profile.get("profile_name") or "",
        "profile_handle": profile.get("handle") or "",
        "profile_followers": profile.get("followers"),
        "profile_bio": (profile.get("bio") or "")[:300] or None,
        "profile_external_links": profile.get("external_links") or [],
        "search_query_used": search.get("search_query") or "",
        "search_results_count": int(search.get("search_results_count") or 0),
        "search_blocked": bool(search.get("blocked")),
        "selected_match": selected or None,
        "match_confidence": (match or {}).get("match_confidence") or "",
        "match_score": (match or {}).get("match_score"),
        "matched_shop_name": (match or {}).get("shop_name") or "",
        "tiktok_shop_url": (match or {}).get("shop_url") or "",
        "voucher_detection_result": voucher_detection,
        "voucher_status": voucher_status,
        "final_url": shop_fetch.get("final_url") or profile_url,
        "http_status": shop_fetch.get("http_status"),
        "page_title": (shop_fetch.get("page_title") or profile.get("page_title") or "")[:200],
        "html_loaded": bool(shop_fetch.get("html_loaded")),
        "html_length": int(shop_fetch.get("html_length") or 0),
        "visible_text_length": int(shop_fetch.get("visible_text_length") or 0),
        "tiktok_blocked": bool(shop_fetch.get("tiktok_blocked")),
        "login_required": bool(shop_fetch.get("login_required")),
        "voucher_keywords_found": bool(detection.get("voucher_keywords_found")),
        "matched_keywords": list(detection.get("matched_keywords") or [])[:12],
        "dom_voucher_found": bool(detection.get("dom_voucher_found")),
        "dom_matches": list(detection.get("dom_matches") or [])[:8],
        "used_playwright": bool(shop_fetch.get("used_playwright")),
        "used_http": bool(shop_fetch.get("used_http")),
        "redirect_chain": list(shop_fetch.get("redirect_chain") or [])[:8],
        "fetch_error": (shop_fetch.get("fetch_error") or search.get("error") or "")[:120] or None,
        "summary": summary,
    }


def public_check_reason(fetch: dict[str, Any], detection: dict[str, Any], voucher_status: str) -> dict[str, Any]:
    """Legacy single-URL check reason (kept for compatibility)."""
    vis_len = int(fetch.get("visible_text_length") or 0)
    parts = []
    if fetch.get("used_playwright"):
        parts.append("Playwright")
    if fetch.get("used_http"):
        parts.append("HTTP")
    if fetch.get("html_loaded"):
        parts.append(f"HTML {fetch.get('html_length', 0)} chars")
    if detection.get("voucher_keywords_found"):
        parts.append("Keywords found")
    parts.append(voucher_status.replace("_", " "))

    return {
        "final_url": fetch.get("final_url") or "",
        "http_status": fetch.get("http_status"),
        "page_title": (fetch.get("page_title") or "")[:200],
        "html_loaded": bool(fetch.get("html_loaded")),
        "html_length": int(fetch.get("html_length") or 0),
        "visible_text_length": vis_len,
        "tiktok_blocked": bool(fetch.get("tiktok_blocked")),
        "login_required": bool(fetch.get("login_required")),
        "voucher_keywords_found": bool(detection.get("voucher_keywords_found")),
        "matched_keywords": list(detection.get("matched_keywords") or [])[:12],
        "dom_voucher_found": bool(detection.get("dom_voucher_found")),
        "dom_matches": list(detection.get("dom_matches") or [])[:8],
        "used_playwright": bool(fetch.get("used_playwright")),
        "used_http": bool(fetch.get("used_http")),
        "redirect_chain": list(fetch.get("redirect_chain") or [])[:8],
        "fetch_error": (fetch.get("fetch_error") or "")[:120] or None,
        "summary": " | ".join(parts),
    }
