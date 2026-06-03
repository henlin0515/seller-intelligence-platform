"""Fuzzy similarity between sheet TikTok names and FastMoss shop candidates."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from seller.fastmoss.match_keywords import generate_search_keywords


def normalize_name(value: str) -> str:
    text = (value or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def compact_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def name_similarity(query: str, candidate: str) -> float:
    q = normalize_name(query)
    c = normalize_name(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    ratio = SequenceMatcher(None, q, c).ratio()
    cq, cc = compact_name(query), compact_name(candidate)
    if cq and cc:
        if cq == cc:
            return max(ratio, 1.0)
        if cq in cc or cc in cq:
            ratio = max(ratio, 0.88)
    return ratio


def token_overlap_score(query: str, candidate: str) -> float:
    qt = {t for t in normalize_name(query).split() if len(t) >= 2}
    ct = {t for t in normalize_name(candidate).split() if len(t) >= 2}
    if not qt or not ct:
        return 0.0
    overlap = len(qt & ct)
    return overlap / max(len(qt), 1)


def candidate_similarity(query: str, candidate: dict[str, Any]) -> float:
    """Best score across shop name, handle, unique_id, and company fields."""
    fields = [
        candidate.get("fastmoss_shop_name"),
        candidate.get("fastmoss_handle"),
        candidate.get("fastmoss_unique_id"),
        candidate.get("seller_company"),
    ]
    scores: list[float] = []
    for field in fields:
        text = str(field or "").strip()
        if not text:
            continue
        scores.append(name_similarity(query, text))
        scores.append(token_overlap_score(query, text))

    # Also compare against keyword variants (handles FS.STORE23 vs FS STORE23).
    for keyword in generate_search_keywords(query, max_keywords=6):
        for field in fields:
            text = str(field or "").strip()
            if text:
                scores.append(name_similarity(keyword, text))

    return max(scores) if scores else 0.0


def rank_candidates(
    tiktok_shop_name: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        score = round(candidate_similarity(tiktok_shop_name, candidate), 4)
        ranked.append({**candidate, "confidence": score})
    ranked.sort(
        key=lambda row: (
            float(row.get("confidence") or 0),
            str(row.get("fastmoss_shop_name") or ""),
        ),
        reverse=True,
    )
    return ranked
