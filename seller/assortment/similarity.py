from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

# Plug-in point for future image embedding / perceptual hash from scraper pipeline.


def normalize_title(text: str) -> str:
    t = (text or "").lower().strip()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def title_similarity(a: str, b: str) -> float:
    """0–100."""
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 100.0
    return round(SequenceMatcher(None, na, nb).ratio() * 100, 2)


def _parse_sku_list(raw: str | list[Any] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip().lower() for x in raw if str(x).strip()]
    s = str(raw).strip()
    if not s:
        return []
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return [str(x).strip().lower() for x in parsed if str(x).strip()]
    except json.JSONDecodeError:
        pass
    return [p.strip().lower() for p in re.split(r"[,;|/]", s) if p.strip()]


def sku_similarity(a: str | list[Any] | None, b: str | list[Any] | None) -> float:
    """0–100 token overlap on SKU variations."""
    sa, sb = set(_parse_sku_list(a)), set(_parse_sku_list(b))
    if not sa and not sb:
        return 0.0
    if not sa or not sb:
        return 0.0
    if sa == sb:
        return 100.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return round((inter / union) * 100, 2) if union else 0.0


def _image_key(url: str | None) -> str:
    if not url:
        return ""
    path = urlparse(url).path.lower()
    name = path.rsplit("/", 1)[-1]
    return re.sub(r"[^a-z0-9]", "", name)


def image_similarity(
    url_a: str | None,
    url_b: str | None,
    *,
    provider: Any | None = None,
) -> float:
    """
    0–100. Default stub compares normalized image URL keys.
    Future: pass ImageSimilarityProvider from scraper/ML module via `provider`.
    """
    if provider is not None and hasattr(provider, "compare"):
        return float(provider.compare(url_a, url_b))

    if not url_a or not url_b:
        return 0.0
    if url_a.strip() == url_b.strip():
        return 100.0
    ka, kb = _image_key(url_a), _image_key(url_b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 95.0
    return round(SequenceMatcher(None, ka, kb).ratio() * 100, 2)
