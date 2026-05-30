from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from seller.competitor_tracker.utils import normalize_name, token_set

MIN_MATCH_SCORE = 0.38


def score_shop_candidate(
    *,
    profile_name: str,
    handle: str,
    sheet_shop_name: str,
    candidate_name: str,
    candidate_url: str = "",
    profile_avatar: str = "",
    candidate_avatar: str = "",
) -> tuple[float, str]:
    """
    Score 0–1 and confidence High | Medium | Low.
    """
    pn = normalize_name(profile_name)
    sn = normalize_name(sheet_shop_name)
    cn = normalize_name(candidate_name)
    h = normalize_name(handle)

    score = 0.0

    if cn and pn and cn == pn:
        score = 1.0
    elif cn and sn and cn == sn:
        score = 0.98
    elif cn and pn and (pn in cn or cn in pn):
        score = max(score, 0.88)
    elif cn and sn and (sn in cn or cn in sn):
        score = max(score, 0.85)
    elif cn and h and (h in cn or cn == h):
        score = max(score, 0.82)

    if score < 0.9 and cn and pn:
        ratio = SequenceMatcher(None, pn, cn).ratio()
        score = max(score, ratio * 0.95)
    if score < 0.9 and cn and sn:
        ratio = SequenceMatcher(None, sn, cn).ratio()
        score = max(score, ratio * 0.92)

    pt = token_set(profile_name)
    st = token_set(sheet_shop_name)
    ct = token_set(candidate_name)
    if ct and pt:
        overlap = len(ct & pt) / max(len(ct | pt), 1)
        score = max(score, overlap * 0.9)
    if ct and st:
        overlap = len(ct & st) / max(len(ct | st), 1)
        score = max(score, overlap * 0.88)

    if profile_avatar and candidate_avatar and profile_avatar == candidate_avatar:
        score = min(1.0, score + 0.08)

    if handle and candidate_url and handle.lower() in candidate_url.lower():
        score = max(score, 0.75)

    if score >= 0.88:
        confidence = "High"
    elif score >= 0.62:
        confidence = "Medium"
    elif score >= MIN_MATCH_SCORE:
        confidence = "Low"
    else:
        confidence = "Low"
        score = score

    return round(score, 3), confidence


def pick_best_shop_match(
    profile: dict[str, Any],
    sheet_shop_name: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not candidates:
        return None

    best: dict[str, Any] | None = None
    best_score = 0.0

    for cand in candidates:
        score, confidence = score_shop_candidate(
            profile_name=profile.get("profile_name") or "",
            handle=profile.get("handle") or "",
            sheet_shop_name=sheet_shop_name,
            candidate_name=cand.get("shop_name") or "",
            candidate_url=cand.get("shop_url") or "",
            profile_avatar=profile.get("avatar_url") or "",
            candidate_avatar=cand.get("avatar_url") or "",
        )
        if score > best_score:
            best_score = score
            best = {**cand, "match_score": score, "match_confidence": confidence}

    if not best or best_score < MIN_MATCH_SCORE:
        return None
    return best
