from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import unquote, urlparse


def extract_handle_from_url(url: str) -> str:
    """Parse @handle from tiktok.com/@handle profile URLs."""
    if not url:
        return ""
    path = urlparse(url).path.strip("/")
    if path.startswith("@"):
        return path[1:].split("/")[0]
    parts = path.split("/")
    for i, p in enumerate(parts):
        if p.startswith("@") and len(p) > 1:
            return p[1:]
        if p == "@" and i + 1 < len(parts):
            return parts[i + 1]
    return ""


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def token_set(name: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if len(t) >= 2}


def parse_json_blobs_from_html(html: str) -> list[Any]:
    """Extract JSON objects embedded in TikTok HTML script tags."""
    blobs: list[Any] = []
    if not html:
        return blobs
    patterns = (
        r'<script[^>]*id=["\']SIGI_STATE["\'][^>]*>(\{.*?\})</script>',
        r'<script[^>]*id=["\']__UNIVERSAL_DATA_FOR_REHYDRATION__["\'][^>]*>(\{.*?\})</script>',
        r'"UserModule":(\{.*?\})\s*[,}]',
    )
    for pat in patterns:
        for m in re.finditer(pat, html, re.DOTALL):
            raw = m.group(1)
            try:
                blobs.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return blobs


def deep_find_keys(obj: Any, keys: tuple[str, ...], max_depth: int = 12) -> list[Any]:
    """Collect values for matching keys in nested dict/list JSON."""
    found: list[Any] = []
    if max_depth <= 0:
        return found

    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys:
                found.append(v)
            found.extend(deep_find_keys(v, keys, max_depth - 1))
    elif isinstance(obj, list):
        for item in obj[:80]:
            found.extend(deep_find_keys(item, keys, max_depth - 1))
    return found


def safe_http_url(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("//"):
        return "https:" + u
    return u
