"""Map seller master TikTok shop names to FastMoss shop IDs."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from seller.fastmoss.match_keywords import generate_search_keywords
from seller.fastmoss.match_scoring import (
    candidate_similarity,
    name_similarity,
    normalize_name,
    rank_candidates,
)
from seller.fastmoss.search import REQUEST_DELAY_SEC, search_shops

if TYPE_CHECKING:
    from seller.intelligence.seller_master import SellerMasterRecord

logger = logging.getLogger("seller.fastmoss.mapping")

DEFAULT_MAPPING_PATH = Path("fastmoss_mapping.json")
MAPPING_MAPPED = "MAPPED"
MAPPING_NEED_REVIEW = "NEED_REVIEW"
MAPPING_NOT_FOUND = "NOT_FOUND"

# REVIEW in UI/docs = NEED_REVIEW in persisted JSON.
MAPPING_REVIEW = MAPPING_NEED_REVIEW

MAPPED_MIN_SCORE = float(os.getenv("FASTMOSS_MAPPED_MIN_SCORE", "0.68"))
REVIEW_MIN_SCORE = float(os.getenv("FASTMOSS_REVIEW_MIN_SCORE", "0.38"))
WEAK_REVIEW_MIN_SCORE = float(os.getenv("FASTMOSS_WEAK_REVIEW_MIN_SCORE", "0.30"))
AMBIGUOUS_GAP = float(os.getenv("FASTMOSS_AMBIGUOUS_GAP", "0.08"))
MATCH_MAX_KEYWORDS = int(os.getenv("FASTMOSS_MATCH_MAX_KEYWORDS", "12"))

_STATUS_RANK = {MAPPING_MAPPED: 3, MAPPING_NEED_REVIEW: 2, MAPPING_NOT_FOUND: 1}


def load_fastmoss_mapping(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_MAPPING_PATH
    with target.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_fastmoss_mapping(payload: dict[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path) if path else DEFAULT_MAPPING_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return target.resolve()


def _normalize_name(value: str) -> str:
    return normalize_name(value)


def _name_similarity(query: str, candidate_name: str) -> float:
    return name_similarity(query, candidate_name)


def needs_fastmoss_rematch(existing: dict[str, Any] | None, seller: Any) -> bool:
    """Re-search FastMoss for MAPPED rows that were rejected or clearly wrong."""
    if not existing:
        return False
    from seller.fastmoss.review import (
        AUDIT_LIKELY_WRONG,
        REVIEW_REJECTED,
        classify_audit_status,
        get_review_by_shop_id,
    )

    review = get_review_by_shop_id(str(getattr(seller, "shop_id", "") or ""))
    if str((review or {}).get("review_status") or "").upper() == REVIEW_REJECTED:
        return True
    audit = classify_audit_status(existing)
    return str(audit.get("audit_status") or "").upper() == AUDIT_LIKELY_WRONG


def should_retry_fastmoss_mapping(
    seller: SellerMasterRecord,
    existing: dict[str, Any] | None,
    *,
    force_refresh_all: bool = False,
    unresolved_only: bool = False,
    not_found_only: bool = False,
) -> bool:
    """Whether to run FastMoss search again for this seller."""
    if existing and existing.get("manual_override"):
        return False
    if force_refresh_all:
        return True
    if existing is None:
        return True
    status = str(existing.get("mapping_status") or MAPPING_NOT_FOUND).upper()
    if unresolved_only or not_found_only:
        if not_found_only and not unresolved_only:
            return status == MAPPING_NOT_FOUND
        return status in {MAPPING_NOT_FOUND, MAPPING_NEED_REVIEW}
    current_tiktok = str(seller.tiktok_shop_name or "").strip()
    existing_tiktok = str(existing.get("tiktok_shop_name") or "").strip()
    if existing_tiktok != current_tiktok:
        return True
    if status == MAPPING_MAPPED:
        return needs_fastmoss_rematch(existing, seller)
    if status in {MAPPING_NOT_FOUND, MAPPING_NEED_REVIEW}:
        return True
    if not str(existing.get("fastmoss_shop_id") or "").strip():
        return True
    return False


def _is_exact_name_match(query: str, candidate: str | dict[str, Any]) -> bool:
    q = normalize_name(query)
    if not q:
        return False
    if isinstance(candidate, str):
        return normalize_name(candidate) == q
    fields = (
        candidate.get("fastmoss_shop_name"),
        candidate.get("fastmoss_handle"),
        candidate.get("fastmoss_unique_id"),
    )
    for field in fields:
        if field and normalize_name(str(field)) == q:
            return True
    return False


def _find_exact_match(
    tiktok_shop_name: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for candidate in candidates:
        if _is_exact_name_match(tiktok_shop_name, candidate):
            return {**candidate, "confidence": 1.0}
    return None


def _decide_status(ranked: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None, str | None]:
    if not ranked:
        return MAPPING_NOT_FOUND, None, "no_fastmoss_results"

    best = ranked[0]
    score = float(best.get("confidence") or 0)
    second_score = float(ranked[1].get("confidence") or 0) if len(ranked) > 1 else 0.0

    if score >= MAPPED_MIN_SCORE:
        if len(ranked) > 1 and score - second_score < AMBIGUOUS_GAP and second_score >= REVIEW_MIN_SCORE:
            return MAPPING_NEED_REVIEW, best, "ambiguous_high_confidence"
        return MAPPING_MAPPED, best, None

    if score >= REVIEW_MIN_SCORE:
        if len(ranked) > 1 and score - second_score < AMBIGUOUS_GAP:
            return MAPPING_NEED_REVIEW, best, "ambiguous_medium_confidence"
        return MAPPING_NEED_REVIEW, best, None

    if score >= WEAK_REVIEW_MIN_SCORE:
        return MAPPING_NEED_REVIEW, best, "weak_match_needs_review"

    return MAPPING_NOT_FOUND, None, f"best_score_below_{WEAK_REVIEW_MIN_SCORE}"


def _collect_candidates_multi_search(
    tiktok_shop_name: str,
    *,
    delay_sec: float = REQUEST_DELAY_SEC,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Run multiple FastMoss searches; return (merged candidates, per-keyword attempt log).
    """
    keywords = generate_search_keywords(tiktok_shop_name, max_keywords=MATCH_MAX_KEYWORDS)
    merged: dict[str, dict[str, Any]] = {}
    attempts: list[dict[str, Any]] = []

    for index, keyword in enumerate(keywords):
        if index > 0 and delay_sec > 0:
            time.sleep(delay_sec)
        rows = search_shops(keyword)
        attempts.append(
            {
                "keyword": keyword,
                "results_count": len(rows),
            }
        )
        for row in rows:
            sid = str(row.get("fastmoss_shop_id") or "").strip()
            if not sid:
                continue
            prev = merged.get(sid)
            if prev is None:
                merged[sid] = {**row, "found_via_keywords": [keyword]}
            else:
                kws = list(prev.get("found_via_keywords") or [])
                if keyword not in kws:
                    kws.append(keyword)
                prev["found_via_keywords"] = kws

    return list(merged.values()), attempts


def _build_not_found_debug(
    tiktok_shop_name: str,
    *,
    keywords_tried: list[str],
    search_attempts: list[dict[str, Any]],
    ranked: list[dict[str, Any]],
    failure_reason: str | None,
) -> dict[str, Any]:
    total_results = sum(int(a.get("results_count") or 0) for a in search_attempts)
    rejections: list[dict[str, Any]] = []
    for row in ranked[:5]:
        rejections.append(
            {
                "fastmoss_shop_name": row.get("fastmoss_shop_name"),
                "fastmoss_handle": row.get("fastmoss_handle"),
                "confidence": row.get("confidence"),
                "reason": failure_reason or "score_too_low",
            }
        )
    return {
        "original_shop_name": tiktok_shop_name,
        "search_keywords_tried": keywords_tried,
        "search_attempts": search_attempts,
        "total_fastmoss_results": total_results,
        "top_candidates_rejected": rejections,
        "failure_reason": failure_reason,
    }


def map_seller_to_fastmoss(
    seller: SellerMasterRecord,
    *,
    candidates: list[dict[str, Any]] | None = None,
    search_attempts: list[dict[str, Any]] | None = None,
    keywords_tried: list[str] | None = None,
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
        "search_keyword_used": None,
        "search_keywords_tried": [],
        "failure_reason": None,
        "match_debug": None,
    }

    tiktok_name = (seller.tiktok_shop_name or "").strip()
    if not tiktok_name:
        base["failure_reason"] = "empty_tiktok_shop_name"
        return base

    if candidates is None:
        keywords = generate_search_keywords(tiktok_name, max_keywords=MATCH_MAX_KEYWORDS)
        found, attempts = _collect_candidates_multi_search(tiktok_name)
        keywords_tried = keywords
        search_attempts = attempts
    else:
        found = candidates
        keywords_tried = keywords_tried or [tiktok_name]
        search_attempts = search_attempts or []

    base["search_keywords_tried"] = keywords_tried

    exact = _find_exact_match(tiktok_name, found)
    if exact:
        status, match, failure = MAPPING_MAPPED, exact, None
    else:
        ranked = rank_candidates(tiktok_name, found)
        status, match, failure = _decide_status(ranked)

    base["mapping_status"] = status
    base["failure_reason"] = failure
    if match:
        base["fastmoss_shop_name"] = match.get("fastmoss_shop_name")
        base["fastmoss_shop_id"] = match.get("fastmoss_shop_id")
        base["fastmoss_shop_url"] = match.get("fastmoss_shop_url")
        base["confidence"] = match.get("confidence")
        via = match.get("found_via_keywords") or []
        base["search_keyword_used"] = via[0] if via else (keywords_tried[0] if keywords_tried else tiktok_name)

    if status == MAPPING_NOT_FOUND:
        ranked = rank_candidates(tiktok_name, found)
        base["match_debug"] = _build_not_found_debug(
            tiktok_name,
            keywords_tried=keywords_tried,
            search_attempts=search_attempts,
            ranked=ranked,
            failure_reason=failure,
        )

    return base


def _status_rank(status: str | None) -> int:
    return _STATUS_RANK.get(str(status or "").upper(), 0)


def _merge_mapping_row(
    existing: dict[str, Any] | None,
    new_row: dict[str, Any],
) -> dict[str, Any]:
    """Keep strong existing MAPPED rows; never replace with weaker NOT_FOUND."""
    if not existing:
        return new_row
    if existing.get("manual_override"):
        return existing

    ex_status = str(existing.get("mapping_status") or "").upper()
    new_status = str(new_row.get("mapping_status") or "").upper()
    ex_conf = float(existing.get("confidence") or 0)
    new_conf = float(new_row.get("confidence") or 0)

    if ex_status == MAPPING_MAPPED and ex_conf >= MAPPED_MIN_SCORE:
        if _status_rank(new_status) < _status_rank(ex_status) or new_conf < ex_conf:
            return existing

    if ex_status == MAPPING_NEED_REVIEW and new_status == MAPPING_NOT_FOUND:
        if ex_conf >= new_conf:
            return existing

    if _status_rank(new_status) > _status_rank(ex_status):
        return new_row
    if _status_rank(new_status) == _status_rank(ex_status) and new_conf > ex_conf:
        return new_row
    if new_status == ex_status and new_conf > ex_conf:
        return new_row
    return existing if ex_conf >= new_conf else new_row


def build_fastmoss_mapping(
    sellers: list[SellerMasterRecord] | None = None,
    *,
    delay_sec: float = REQUEST_DELAY_SEC,
) -> dict[str, Any]:
    """Search FastMoss for every seller master row and return mapping payload."""
    from seller.intelligence.seller_master import get_seller_master

    loaded = get_seller_master(force_refresh=True) if sellers is None else None
    rows_in = sellers if sellers is not None else loaded.sellers  # type: ignore[union-attr]

    mappings: list[dict[str, Any]] = []
    for index, seller in enumerate(rows_in):
        if index > 0 and delay_sec > 0:
            time.sleep(delay_sec)
        mappings.append(map_seller_to_fastmoss(seller))

    counts = _summary_counts(mappings)
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "region": "PH",
        "source": "seller_master_google_sheet",
        "summary": counts,
        "mappings": mappings,
    }


def _summary_counts(mappings: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(mappings),
        "mapped": sum(1 for row in mappings if row["mapping_status"] == MAPPING_MAPPED),
        "need_review": sum(1 for row in mappings if row["mapping_status"] == MAPPING_NEED_REVIEW),
        "not_found": sum(1 for row in mappings if row["mapping_status"] == MAPPING_NOT_FOUND),
    }


def refresh_fastmoss_mapping(
    *,
    force_refresh_all: bool = False,
    unresolved_only: bool = False,
    not_found_only: bool = False,
    mapping_path: str | Path | None = None,
    delay_sec: float = REQUEST_DELAY_SEC,
) -> dict[str, Any]:
    """
    Retry FastMoss search for unmapped sellers.
    When ``unresolved_only=True``, only NOT_FOUND and NEED_REVIEW rows are searched.
    """
    from seller.fastmoss.review import sync_reviews_from_mappings
    from seller.intelligence.seller_master import get_seller_master

    master = get_seller_master(force_refresh=True)
    target = Path(mapping_path) if mapping_path else DEFAULT_MAPPING_PATH

    try:
        existing_payload = load_fastmoss_mapping(target)
    except OSError:
        existing_payload = {"mappings": []}

    existing_by_shop: dict[str, dict[str, Any]] = {}
    for row in existing_payload.get("mappings") or []:
        if not isinstance(row, dict):
            continue
        shop_id = str(row.get("shop_id") or "").strip()
        if shop_id:
            existing_by_shop[shop_id] = row

    mappings: list[dict[str, Any]] = []
    newly_mapped_shop_ids: list[str] = []
    upgraded_to_review: list[str] = []
    processed_count = 0
    debug_not_found: list[dict[str, Any]] = []

    for index, seller in enumerate(master.sellers):
        existing = existing_by_shop.get(seller.shop_id)
        if not should_retry_fastmoss_mapping(
            seller,
            existing,
            force_refresh_all=force_refresh_all,
            unresolved_only=unresolved_only,
            not_found_only=not_found_only,
        ):
            mappings.append(existing)  # type: ignore[arg-type]
            continue

        processed_count += 1
        if processed_count > 1 and delay_sec > 0:
            time.sleep(delay_sec)

        prior_status = str((existing or {}).get("mapping_status") or MAPPING_NOT_FOUND).upper()
        new_row = map_seller_to_fastmoss(seller)
        row = _merge_mapping_row(existing, new_row)
        mappings.append(row)

        new_status = str(row.get("mapping_status") or "").upper()
        if new_status == MAPPING_MAPPED and prior_status != MAPPING_MAPPED:
            newly_mapped_shop_ids.append(seller.shop_id)
        if new_status == MAPPING_NEED_REVIEW and prior_status == MAPPING_NOT_FOUND:
            upgraded_to_review.append(seller.shop_id)
        if new_status == MAPPING_NOT_FOUND and row.get("match_debug"):
            debug_not_found.append(
                {
                    "shop_id": seller.shop_id,
                    "shop_name": seller.shop_name,
                    "tiktok_shop_name": seller.tiktok_shop_name,
                    **row.get("match_debug"),
                }
            )

    counts = _summary_counts(mappings)
    mapping_payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "region": "PH",
        "source": "seller_master_google_sheet",
        "summary": counts,
        "mappings": mappings,
        "not_found_debug": debug_not_found,
    }
    persist_payload = {k: v for k, v in mapping_payload.items() if k != "not_found_debug"}
    save_fastmoss_mapping(persist_payload, target)

    sync_reviews_from_mappings(mappings)

    return {
        "success": True,
        "processed_count": processed_count,
        "newly_mapped_count": len(newly_mapped_shop_ids),
        "upgraded_to_review_count": len(upgraded_to_review),
        "still_not_found_count": counts["not_found"],
        "not_found_debug_count": len(debug_not_found),
        "tiktok_data_refreshed_count": 0,
        "refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def refresh_all_sheet_fastmoss_mapping(
    *,
    mapping_path: str | Path | None = None,
    delay_sec: float = REQUEST_DELAY_SEC,
) -> dict[str, Any]:
    """
    Reload seller master from sheet and refresh shops that still need FastMoss search.

    Preserves confirmed MAPPED rows; re-searches NOT_FOUND, NEED_REVIEW, rejected/wrong
    MAPPED rows, and rows whose TikTok name changed on the sheet.
    """
    return refresh_fastmoss_mapping(
        force_refresh_all=False,
        unresolved_only=False,
        mapping_path=mapping_path,
        delay_sec=delay_sec,
    )


def refresh_unresolved_fastmoss_mapping(
    *,
    mapping_path: str | Path | None = None,
    delay_sec: float = REQUEST_DELAY_SEC,
) -> dict[str, Any]:
    """Re-run multi-keyword FastMoss search for NOT_FOUND and NEED_REVIEW only."""
    return refresh_fastmoss_mapping(
        force_refresh_all=False,
        unresolved_only=True,
        mapping_path=mapping_path,
        delay_sec=delay_sec,
    )


def refresh_not_found_fastmoss_mapping(
    *,
    mapping_path: str | Path | None = None,
    delay_sec: float = REQUEST_DELAY_SEC,
) -> dict[str, Any]:
    """Alias for ``refresh_unresolved_fastmoss_mapping`` (includes NEED_REVIEW)."""
    return refresh_unresolved_fastmoss_mapping(
        mapping_path=mapping_path,
        delay_sec=delay_sec,
    )
