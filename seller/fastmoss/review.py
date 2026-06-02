"""FastMoss mapping review, audit classification, and persistent approvals."""

from __future__ import annotations

import json
import os
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from seller.fastmoss.mapping import (
    MAPPING_MAPPED,
    MAPPING_NOT_FOUND,
    DEFAULT_MAPPING_PATH,
    _is_exact_name_match,
    _name_similarity,
    load_fastmoss_mapping,
    save_fastmoss_mapping,
)

REVIEW_APPROVED = "APPROVED"
REVIEW_PENDING = "PENDING_REVIEW"
REVIEW_REJECTED = "REJECTED"

AUDIT_CONFIRMED = "CONFIRMED_MATCH"
AUDIT_NEEDS_REVIEW = "NEEDS_REVIEW"
AUDIT_LIKELY_WRONG = "LIKELY_WRONG"

DEFAULT_REVIEW_PATH = Path(
    os.getenv("FASTMOSS_MAPPING_REVIEW_PATH", "mapping_review_status.json")
)

AUTO_APPROVE_MIN_CONFIDENCE = 0.95
AUTO_APPROVE_MIN_SIMILARITY = 0.95
PENDING_MIN_SIMILARITY = 0.70
REJECT_MAX_SIMILARITY = 0.50


def normalize_name(value: str) -> str:
    text = (value or "").lower().strip()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def name_similarity(a: str, b: str) -> float:
    return _name_similarity(a, b)


def is_abbreviation(a: str, b: str) -> bool:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    ta = {t for t in na.split() if len(t) >= 3}
    tb = {t for t in nb.split() if len(t) >= 3}
    return bool(ta & tb)


def classify_audit_status(row: dict[str, Any]) -> dict[str, Any]:
    """Classify TikTok ↔ FastMoss match quality (read-only audit)."""
    tiktok = str(row.get("tiktok_shop_name") or "")
    fastmoss = str(row.get("fastmoss_shop_name") or "")
    stored_conf = float(row.get("confidence") or 0.0)
    sim_tf = name_similarity(tiktok, fastmoss)
    exact_tf = normalize_name(tiktok) == normalize_name(fastmoss) and bool(normalize_name(tiktok))
    abbrev = is_abbreviation(tiktok, fastmoss)
    reasons: list[str] = []

    if not tiktok or not fastmoss:
        status = AUDIT_LIKELY_WRONG
        reasons.append("Missing TikTok or FastMoss shop name")
    elif sim_tf < REJECT_MAX_SIMILARITY and not abbrev:
        status = AUDIT_LIKELY_WRONG
        reasons.append(
            f"TikTok {tiktok!r} vs FastMoss {fastmoss!r} — low similarity ({sim_tf:.1%})"
        )
    elif exact_tf or sim_tf >= 0.90:
        if stored_conf >= 0.90:
            status = AUDIT_CONFIRMED
            reasons.append(
                "Exact TikTok ↔ FastMoss match"
                if exact_tf
                else f"Very high similarity ({sim_tf:.1%})"
            )
        else:
            status = AUDIT_NEEDS_REVIEW
            reasons.append(f"Strong match but confidence {stored_conf:.2f} < 0.90")
    elif abbrev or PENDING_MIN_SIMILARITY <= sim_tf < 0.90 or stored_conf < 0.90:
        status = AUDIT_NEEDS_REVIEW
        if abbrev:
            reasons.append("Partial / abbreviation match")
        if PENDING_MIN_SIMILARITY <= sim_tf < 0.90:
            reasons.append(f"Moderate similarity ({sim_tf:.1%})")
        if stored_conf < 0.90:
            reasons.append(f"Confidence {stored_conf:.2f} < 0.90")
    else:
        status = AUDIT_NEEDS_REVIEW
        reasons.append("Manual verification recommended")

    return {
        "audit_status": status,
        "tiktok_fastmoss_similarity": round(sim_tf, 4),
        "audit_reason": "; ".join(reasons),
    }


def suggest_review_status(row: dict[str, Any], audit: dict[str, Any] | None = None) -> tuple[str, str]:
    """Return (review_status, reason) for a mapping row."""
    audit = audit or classify_audit_status(row)
    mapping_status = str(row.get("mapping_status") or MAPPING_NOT_FOUND).upper()
    tiktok = str(row.get("tiktok_shop_name") or "")
    fastmoss = str(row.get("fastmoss_shop_name") or "")
    confidence = float(row.get("confidence") or 0.0)
    sim = float(audit.get("tiktok_fastmoss_similarity") or 0.0)
    audit_status = audit.get("audit_status")
    abbrev = is_abbreviation(tiktok, fastmoss)
    exact = _is_exact_name_match(tiktok, fastmoss)

    if mapping_status != MAPPING_MAPPED or not fastmoss:
        return REVIEW_PENDING, "No FastMoss mapping yet"

    if audit_status == AUDIT_LIKELY_WRONG or sim < REJECT_MAX_SIMILARITY:
        return REVIEW_REJECTED, audit.get("audit_reason") or "Likely wrong brand match"

    if exact:
        return REVIEW_APPROVED, "Exact normalized TikTok ↔ FastMoss match"

    if abbrev or audit_status == AUDIT_NEEDS_REVIEW:
        return REVIEW_PENDING, audit.get("audit_reason") or "Needs manual review"

    if (
        confidence >= AUTO_APPROVE_MIN_CONFIDENCE
        and sim >= AUTO_APPROVE_MIN_SIMILARITY
        and audit_status == AUDIT_CONFIRMED
    ):
        return REVIEW_APPROVED, "High confidence exact brand match"

    if PENDING_MIN_SIMILARITY <= sim < AUTO_APPROVE_MIN_SIMILARITY:
        return REVIEW_PENDING, audit.get("audit_reason") or "Moderate similarity — needs review"

    return REVIEW_PENDING, audit.get("audit_reason") or "Default pending review"


def allows_tiktok_data(review_status: str | None) -> bool:
    return str(review_status or "").upper() == REVIEW_APPROVED


def load_review_store(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_REVIEW_PATH
    if not target.is_file():
        return {"version": 1, "updated_at": None, "reviews": {}}
    with target.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_review_store(payload: dict[str, Any], path: Path | None = None) -> Path:
    target = path or DEFAULT_REVIEW_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload["version"] = 1
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return target.resolve()


def get_review_by_shop_id(shop_id: str, store: dict[str, Any] | None = None) -> dict[str, Any] | None:
    data = store if store is not None else load_review_store()
    row = (data.get("reviews") or {}).get(str(shop_id))
    return dict(row) if isinstance(row, dict) else None


def _mapping_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("tiktok_shop_name") or ""),
        str(row.get("fastmoss_shop_id") or ""),
        str(row.get("fastmoss_shop_name") or ""),
    )


def preserve_manual_review(existing: dict[str, Any] | None, mapping_row: dict[str, Any]) -> bool:
    if not existing:
        return False
    prior = str(existing.get("review_status") or "")
    if prior not in {REVIEW_APPROVED, REVIEW_REJECTED}:
        return False
    if not existing.get("reviewed_by"):
        return False
    return _mapping_identity(existing) == _mapping_identity(mapping_row)


def upsert_review_from_mapping(
    mapping_row: dict[str, Any],
    *,
    store: dict[str, Any] | None = None,
    reviewed_by: str | None = None,
    notes: str | None = None,
    force_status: str | None = None,
) -> dict[str, Any]:
    data = store if store is not None else load_review_store()
    reviews: dict[str, Any] = data.setdefault("reviews", {})
    shop_id = str(mapping_row.get("shop_id") or "")
    existing = reviews.get(shop_id) if isinstance(reviews.get(shop_id), dict) else None
    audit = classify_audit_status(mapping_row)

    if force_status:
        review_status = force_status
        reason = notes or f"Set to {force_status}"
    elif preserve_manual_review(existing, mapping_row):
        review_status = str(existing.get("review_status"))
        reason = str(existing.get("notes") or "Manual review preserved")
    else:
        review_status, reason = suggest_review_status(mapping_row, audit)

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record: dict[str, Any] = {
        "shop_id": shop_id,
        "shop_name": mapping_row.get("shop_name"),
        "tiktok_shop_name": mapping_row.get("tiktok_shop_name"),
        "fastmoss_shop_id": mapping_row.get("fastmoss_shop_id"),
        "fastmoss_shop_name": mapping_row.get("fastmoss_shop_name"),
        "mapping_status": mapping_row.get("mapping_status"),
        "confidence": mapping_row.get("confidence"),
        "audit_status": audit["audit_status"],
        "audit_reason": audit["audit_reason"],
        "tiktok_fastmoss_similarity": audit["tiktok_fastmoss_similarity"],
        "review_status": review_status,
        "reviewed_by": reviewed_by or (existing or {}).get("reviewed_by"),
        "reviewed_at": (existing or {}).get("reviewed_at") if preserve_manual_review(existing, mapping_row) else None,
        "notes": notes or reason,
        "updated_at": now,
    }
    if reviewed_by:
        record["reviewed_by"] = reviewed_by
        record["reviewed_at"] = now
    reviews[shop_id] = record
    return record


def sync_reviews_from_mappings(
    mappings: list[dict[str, Any]],
    *,
    store: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = store if store is not None else load_review_store()
    master_by_shop: dict[str, Any] = {}
    try:
        from seller.intelligence.seller_master import get_seller_master

        master = get_seller_master()
        master_by_shop = {str(s.shop_id): s for s in master.sellers}
    except Exception:
        master_by_shop = {}

    for row in mappings:
        if not isinstance(row, dict):
            continue
        audit_row = dict(row)
        seller = master_by_shop.get(str(row.get("shop_id") or ""))
        if seller and str(seller.tiktok_shop_name or "").strip():
            audit_row["tiktok_shop_name"] = seller.tiktok_shop_name
        upsert_review_from_mapping(audit_row, store=data)
    save_review_store(data)
    return data


def set_review_decision(
    shop_id: str,
    *,
    review_status: str,
    reviewed_by: str,
    notes: str | None = None,
    fastmoss_shop_id: str | None = None,
    fastmoss_shop_name: str | None = None,
    fastmoss_shop_url: str | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    """Persist approve/reject/select and update fastmoss_mapping.json when candidate chosen."""
    mapping_payload = load_fastmoss_mapping()
    mapping_row = None
    for row in mapping_payload.get("mappings") or []:
        if str(row.get("shop_id")) == str(shop_id):
            mapping_row = row
            break
    if mapping_row is None:
        raise KeyError(f"Shop {shop_id} not found in mapping file")

    if fastmoss_shop_id:
        mapping_row["fastmoss_shop_id"] = fastmoss_shop_id
        mapping_row["fastmoss_shop_name"] = fastmoss_shop_name
        mapping_row["fastmoss_shop_url"] = fastmoss_shop_url
        mapping_row["mapping_status"] = MAPPING_MAPPED
        if confidence is not None:
            mapping_row["confidence"] = confidence
        save_fastmoss_mapping(mapping_payload)

    data = load_review_store()
    record = upsert_review_from_mapping(
        mapping_row,
        store=data,
        reviewed_by=reviewed_by,
        notes=notes,
        force_status=review_status,
    )
    record["reviewed_by"] = reviewed_by
    record["reviewed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record["review_status"] = review_status
    if notes:
        record["notes"] = notes
    data["reviews"][shop_id] = record
    save_review_store(data)
    return record


def review_summary(store: dict[str, Any] | None = None) -> dict[str, int]:
    data = store if store is not None else load_review_store()
    reviews = list((data.get("reviews") or {}).values())
    mapped = [r for r in reviews if str(r.get("mapping_status") or "").upper() == MAPPING_MAPPED]
    return {
        "total": len(reviews),
        "mapped": len(mapped),
        REVIEW_APPROVED: sum(1 for r in reviews if r.get("review_status") == REVIEW_APPROVED),
        REVIEW_PENDING: sum(1 for r in reviews if r.get("review_status") == REVIEW_PENDING),
        REVIEW_REJECTED: sum(1 for r in reviews if r.get("review_status") == REVIEW_REJECTED),
    }


def list_review_rows(store: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = store if store is not None else load_review_store()
    rows = [dict(r) for r in (data.get("reviews") or {}).values() if isinstance(r, dict)]
    order = {REVIEW_REJECTED: 0, REVIEW_PENDING: 1, REVIEW_APPROVED: 2}
    rows.sort(
        key=lambda r: (
            order.get(str(r.get("review_status")), 9),
            str(r.get("shop_name") or "").lower(),
        )
    )
    return rows


def approved_mapping_rows(
    mapping_path: Path | None = None,
    review_path: Path | None = None,
) -> list[dict[str, Any]]:
    payload = load_fastmoss_mapping(mapping_path)
    store = load_review_store(review_path)
    out: list[dict[str, Any]] = []
    for row in payload.get("mappings") or []:
        if str(row.get("mapping_status") or "").upper() != MAPPING_MAPPED:
            continue
        shop_id = str(row.get("shop_id") or "")
        review = get_review_by_shop_id(shop_id, store)
        if review and allows_tiktok_data(review.get("review_status")):
            merged = {**row, **review}
            out.append(merged)
    return out
