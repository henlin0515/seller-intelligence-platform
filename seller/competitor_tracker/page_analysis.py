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
    """Detect TikTok block / login wall from visible text and status."""
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
        # Avoid false positive on footer "Sign in" only — require short page or explicit wall
        if len(page_text) < 2500 or "log in to continue" in combined or "login to view" in combined:
            login_required = True

    return {"tiktok_blocked": blocked, "login_required": login_required}


def build_check_summary(
    *,
    voucher_status: str,
    fetch: dict[str, Any],
    detection: dict[str, Any],
) -> str:
    parts: list[str] = []
    if fetch.get("used_playwright"):
        parts.append("Playwright fetch")
    if fetch.get("used_http"):
        parts.append("HTTP fetch")
    if not fetch.get("used_playwright") and not fetch.get("used_http"):
        parts.append("No successful fetch")

    if fetch.get("html_loaded"):
        parts.append(f"HTML loaded ({fetch.get('html_length', 0)} chars)")
    else:
        parts.append("HTML not loaded")

    if fetch.get("tiktok_blocked"):
        parts.append("TikTok may have blocked access")
    if fetch.get("login_required"):
        parts.append("Login may be required")

    if detection.get("voucher_keywords_found"):
        kw = detection.get("matched_keywords") or []
        parts.append(f"Keywords: {', '.join(kw[:5])}")
    elif detection.get("dom_voucher_found"):
        parts.append("DOM voucher elements detected")
    else:
        parts.append("No voucher keywords/DOM match")

    vis_len = int(fetch.get("visible_text_length") or 0)
    if vis_len < 500 and fetch.get("html_loaded"):
        parts.append(f"SPA shell ({vis_len} visible chars — Playwright needed for full render)")

    parts.append(f"Result: {voucher_status.replace('_', ' ')}")
    return " | ".join(parts)


def public_check_reason(fetch: dict[str, Any], detection: dict[str, Any], voucher_status: str) -> dict[str, Any]:
    """Sanitized diagnostics for API/UI (no stack traces)."""
    return {
        "final_url": fetch.get("final_url") or fetch.get("start_url") or "",
        "http_status": fetch.get("http_status"),
        "page_title": (fetch.get("page_title") or "")[:200],
        "html_loaded": bool(fetch.get("html_loaded")),
        "html_length": int(fetch.get("html_length") or 0),
        "visible_text_length": int(fetch.get("visible_text_length") or 0),
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
        "summary": build_check_summary(
            voucher_status=voucher_status,
            fetch=fetch,
            detection=detection,
        ),
    }
