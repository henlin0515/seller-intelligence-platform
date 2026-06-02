"""Map seller master TikTok shop names to FastMoss shop IDs."""

from __future__ import annotations

import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from seller.fastmoss.search import REQUEST_DELAY_SEC, search_shops
from seller.intelligence.seller_master import SellerMasterRecord, get_seller_master

DEFAULT_MAPPING_PATH = Path("fastmoss_mapping.json")
MAPPING_MAPPED = "MAPPED"
MAPPING_NEED_REVIEW = "NEED_REVIEW"
MAPPING_NOT_FOUND = "NOT_FOUND"

MAPPED_MIN_SCORE = 0.70
REVIEW_MIN_SCORE = 0.40


def load_fastmoss_mapping(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_MAPPING_PATH
    with target.open(encoding="utf-8") as handle:
        return json.load(handle)

def _normalize_name(value: str) -> str:
    text = (value or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _is_exact_name_match(query: str, candidate_name: str) -> bool:
    q = _normalize_name(query)
    c = _normalize_name(candidate_name)
    return bool(q and c and q == c)


def _name_similarity(query: str, candidate_name: str) -> float:
    q = _normalize_name(query)
    c = _normalize_name(candidate_name)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    return SequenceMatcher(None, q, c).ratio()


def _find_exact_match(
    tiktok_shop_name: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for candidate in candidates:
        if _is_exact_name_match(tiktok_shop_name, candidate.get("fastmoss_shop_name", "")):
            return {**candidate, "confidence": 1.0}
    return None


def _rank_candidates(tiktok_shop_name: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        score = _name_similarity(tiktok_shop_name, candidate.get("fastmoss_shop_name", ""))
        ranked.append({**candidate, "confidence": round(score, 4)})
    ranked.sort(key=lambda row: row["confidence"], reverse=True)
    return ranked


def _decide_status(ranked: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    if not ranked:
        return MAPPING_NOT_FOUND, None

    best = ranked[0]
    if best["confidence"] >= MAPPED_MIN_SCORE:
        return MAPPING_MAPPED, best
    if best["confidence"] >= REVIEW_MIN_SCORE:
        return MAPPING_NEED_REVIEW, best
    return MAPPING_NOT_FOUND, None


def map_seller_to_fastmoss(
    seller: SellerMasterRecord,
    *,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one mapping row for a seller master record."""
    base: dict[str, Any] = {
        "shop_id": seller.shop_id,
        "shop_name": seller.shop_name,
        "tiktok_shop_name": seller.tiktok_shop_name,
        "fastmoss_shop_name": None,
        "fastmoss_shop_id": None,
        "fastmoss_shop_url": None,
        "mapping_status": MAPPING_NOT_FOUND,
        "confidence": 0.0,
    }

    tiktok_name = (seller.tiktok_shop_name or "").strip()
    if not tiktok_name:
        return base

    found = candidates if candidates is not None else search_shops(tiktok_name)
    exact = _find_exact_match(tiktok_name, found)
    if exact:
        status, match = MAPPING_MAPPED, exact
    else:
        ranked = _rank_candidates(tiktok_name, found)
        status, match = _decide_status(ranked)

    base["mapping_status"] = status
    if match:
        base["fastmoss_shop_name"] = match["fastmoss_shop_name"]
        base["fastmoss_shop_id"] = match["fastmoss_shop_id"]
        base["fastmoss_shop_url"] = match["fastmoss_shop_url"]
        base["confidence"] = match["confidence"]

    return base


def build_fastmoss_mapping(
    sellers: list[SellerMasterRecord] | None = None,
    *,
    delay_sec: float = REQUEST_DELAY_SEC,
) -> dict[str, Any]:
    """Search FastMoss for every seller master row and return mapping payload."""
    loaded = get_seller_master(force_refresh=True) if sellers is None else None
    rows_in = sellers if sellers is not None else loaded.sellers  # type: ignore[union-attr]

    mappings: list[dict[str, Any]] = []
    for index, seller in enumerate(rows_in):
        if index > 0 and delay_sec > 0:
            time.sleep(delay_sec)
        mappings.append(map_seller_to_fastmoss(seller))

    counts = {
        "total": len(mappings),
        "mapped": sum(1 for row in mappings if row["mapping_status"] == MAPPING_MAPPED),
        "need_review": sum(1 for row in mappings if row["mapping_status"] == MAPPING_NEED_REVIEW),
        "not_found": sum(1 for row in mappings if row["mapping_status"] == MAPPING_NOT_FOUND),
    }

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "region": "PH",
        "source": "seller_master_google_sheet",
        "summary": counts,
        "mappings": mappings,
    }
