from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from seller.competitor_tracker.constants import VOUCHER_KEYWORDS, VOUCHER_PATTERNS
from seller.competitor_tracker.page_analysis import analyze_access_signals

_COMPILED_PATTERNS = [re.compile(p, re.I) for p in VOUCHER_PATTERNS]

# User-requested keyword set (includes symbols)
_SEARCH_KEYWORDS = tuple(
    dict.fromkeys(
        list(VOUCHER_KEYWORDS)
        + ["voucher", "coupon", "discount", "off", "free shipping", "₱", "%", "diskwento", "優惠券", "折扣", "免運"]
    )
)

_DOM_SELECTOR_HINTS = (
    "coupon",
    "voucher",
    "promo",
    "promotion",
    "discount",
    "Voucher",
    "Coupon",
)


def _normalize_page_text(html: str, visible_text: str = "") -> str:
    combined = f"{html}\n{visible_text}"
    combined = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", combined, flags=re.I)
    combined = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", combined, flags=re.I)
    combined = re.sub(r"<[^>]+>", " ", combined)
    combined = re.sub(r"\s+", " ", combined)
    return combined.strip()


def detect_dom_voucher_snippets(html: str) -> list[str]:
    """DOM-based voucher detection for TikTok shop promo elements."""
    if not html or len(html) < 50:
        return []
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return []

    snippets: list[str] = []
    seen: set[str] = set()

    for tag in soup.find_all(True):
        attrs = " ".join(
            filter(
                None,
                [
                    tag.get("class") and " ".join(tag.get("class")),
                    tag.get("id") or "",
                    tag.get("data-e2e") or "",
                    tag.get("aria-label") or "",
                ],
            )
        ).lower()
        if not any(h in attrs for h in _DOM_SELECTOR_HINTS):
            continue
        text = tag.get_text(" ", strip=True)
        if not text or len(text) > 320:
            continue
        if not _text_looks_like_voucher(text):
            continue
        key = text[:120]
        if key in seen:
            continue
        seen.add(key)
        snippets.append(text[:240])

    return snippets[:10]


def _text_looks_like_voucher(text: str) -> bool:
    lower = text.lower()
    if any(kw.lower() in lower for kw in _SEARCH_KEYWORDS if len(kw) > 1):
        return True
    if "₱" in text or "%" in text:
        return True
    if re.search(r"\boff\b", lower) and re.search(r"\d", text):
        return True
    return False


def detect_embedded_html_signals(html: str) -> tuple[list[str], list[str]]:
    """
    TikTok SPAs often hide promos in inline JSON while visible text is nearly empty.
    Scan raw HTML (not only rendered text) for voucher keywords and DOM-like class names.
    """
    if not html or len(html) < 200:
        return [], []
    lower = html.lower()
    matched: list[str] = []
    for kw in _SEARCH_KEYWORDS:
        k = kw.strip()
        if not k or len(k) < 2:
            continue
        if k.lower() in lower:
            matched.append(k)
    dom_hints: list[str] = []
    for hint in ("voucher", "coupon", "promo", "discount"):
        if f'"{hint}"' in lower or f"{hint}" in lower:
            dom_hints.append(f"html:{hint}")
    return list(dict.fromkeys(matched))[:12], dom_hints[:8]


def detect_voucher_signals(
    page_text: str,
    *,
    html: str = "",
    dom_snippets: list[str] | None = None,
) -> dict[str, Any]:
    """
    Keyword + pattern + DOM detection.
    Returns voucher_status found|not_found and diagnostic flags.
    """
    text_lower = page_text.lower()
    matched: list[str] = []

    for kw in _SEARCH_KEYWORDS:
        k = kw.strip()
        if not k:
            continue
        if len(k) <= 2:
            if k in page_text:
                matched.append(k)
        elif k.lower() in text_lower:
            matched.append(k)

    for pat in _COMPILED_PATTERNS:
        m = pat.search(page_text)
        if m:
            matched.append(m.group(0))

    dom_from_html = detect_dom_voucher_snippets(html) if html else []
    all_dom = list(dict.fromkeys((dom_snippets or []) + dom_from_html))[:10]

    if len(page_text) < 800 and html:
        embedded_kw, embedded_dom = detect_embedded_html_signals(html)
        for k in embedded_kw:
            if k not in matched:
                matched.append(k)
        for d in embedded_dom:
            if d not in all_dom:
                all_dom.append(d)

    voucher_keywords_found = len(matched) > 0
    dom_voucher_found = len(all_dom) > 0

    if voucher_keywords_found or dom_voucher_found:
        needle = matched[0] if matched else (all_dom[0] if all_dom else "")
        snippet = _extract_snippet(page_text, needle) if matched else (all_dom[0][:240] if all_dom else "")
        if not snippet and all_dom:
            snippet = all_dom[0][:240]
        return {
            "voucher_status": "found",
            "voucher_text": snippet,
            "matched_keywords": list(dict.fromkeys(matched))[:12],
            "voucher_keywords_found": True,
            "dom_voucher_found": dom_voucher_found,
            "dom_matches": all_dom,
        }

    return {
        "voucher_status": "not_found",
        "voucher_text": "",
        "matched_keywords": [],
        "voucher_keywords_found": False,
        "dom_voucher_found": False,
        "dom_matches": [],
    }


def resolve_voucher_status(
    fetch: dict[str, Any],
    detection: dict[str, Any],
) -> str:
    """Map fetch + detection to found | not_found | unable_to_check."""
    if not fetch.get("ok") and not fetch.get("html_loaded"):
        return "unable_to_check"
    if fetch.get("tiktok_blocked") and not detection.get("voucher_keywords_found") and not detection.get(
        "dom_voucher_found"
    ):
        return "unable_to_check"
    if fetch.get("login_required") and fetch.get("visible_text_length", 0) < 1200:
        if not detection.get("voucher_keywords_found") and not detection.get("dom_voucher_found"):
            return "unable_to_check"
    if detection.get("voucher_status") == "found":
        return "found"
    if fetch.get("html_loaded") or fetch.get("visible_text_length", 0) >= 200:
        return "not_found"
    return "unable_to_check"


def _extract_snippet(text: str, needle: str, radius: int = 80) -> str:
    if not text or not needle:
        return ""
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return str(needle)[:200]
    start = max(0, idx - radius)
    end = min(len(text), idx + len(needle) + radius)
    snippet = text[start:end].strip()
    snippet = re.sub(r"\s+", " ", snippet)
    return snippet[:240]


def enrich_fetch_with_access(fetch: dict[str, Any]) -> dict[str, Any]:
    """Add tiktok_blocked / login_required to fetch dict."""
    signals = analyze_access_signals(
        fetch.get("page_text") or "",
        fetch.get("page_title") or "",
        fetch.get("http_status"),
    )
    fetch.update(signals)
    return fetch
