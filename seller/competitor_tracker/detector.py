from __future__ import annotations

import re
from typing import Any

from seller.competitor_tracker.constants import VOUCHER_KEYWORDS, VOUCHER_PATTERNS

_COMPILED_PATTERNS = [re.compile(p, re.I) for p in VOUCHER_PATTERNS]


def _normalize_page_text(html: str, visible_text: str = "") -> str:
    combined = f"{html}\n{visible_text}"
    combined = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", combined, flags=re.I)
    combined = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", combined, flags=re.I)
    combined = re.sub(r"<[^>]+>", " ", combined)
    combined = re.sub(r"\s+", " ", combined)
    return combined.strip()


def detect_voucher_signals(page_text: str) -> dict[str, Any]:
    """
    Returns voucher_status: found | not_found, voucher_text snippet, matched_terms.
    Caller sets unable_to_check when page_text is empty/unavailable.
    """
    text_lower = page_text.lower()
    matched: list[str] = []

    for kw in VOUCHER_KEYWORDS:
        if kw.lower() in text_lower:
            matched.append(kw.strip())

    for pat in _COMPILED_PATTERNS:
        m = pat.search(page_text)
        if m:
            matched.append(m.group(0))

    if matched:
        snippet = _extract_snippet(page_text, matched[0])
        return {
            "voucher_status": "found",
            "voucher_text": snippet,
            "matched_terms": list(dict.fromkeys(matched))[:8],
        }

    return {
        "voucher_status": "not_found",
        "voucher_text": "",
        "matched_terms": [],
    }


def _extract_snippet(text: str, needle: str, radius: int = 80) -> str:
    if not text or not needle:
        return ""
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return needle[:200]
    start = max(0, idx - radius)
    end = min(len(text), idx + len(needle) + radius)
    snippet = text[start:end].strip()
    snippet = re.sub(r"\s+", " ", snippet)
    return snippet[:240]
