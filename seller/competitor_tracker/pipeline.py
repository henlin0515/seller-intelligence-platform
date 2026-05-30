from __future__ import annotations

import logging
from typing import Any

from seller.competitor_tracker.detector import (
    detect_voucher_signals,
    enrich_fetch_with_access,
    resolve_voucher_status,
)
from seller.competitor_tracker.fetcher import fetch_tiktok_page
from seller.competitor_tracker.page_analysis import public_pipeline_check_reason
from seller.competitor_tracker.profile import fetch_profile
from seller.competitor_tracker.shop_matcher import pick_best_shop_match
from seller.competitor_tracker.shop_search import build_profile_shop_candidates, search_tiktok_shop

logger = logging.getLogger("seller.competitor_tracker.pipeline")


def run_profile_shop_voucher_check(row: dict[str, str]) -> dict[str, Any]:
    """
    Full flow: profile URL -> extract profile -> search TikTok Shop -> match -> voucher detect.
    """
    profile_url = (row.get("tiktok_link") or "").strip()
    sheet_shop_name = (row.get("shop_name") or "").strip()

    profile: dict[str, Any] = {}
    profile_fetch: dict[str, Any] = {}
    search: dict[str, Any] = {}
    match: dict[str, Any] | None = None
    shop_fetch: dict[str, Any] = {}
    detection: dict[str, Any] = {}

    if not profile_url:
        return _result(
            voucher_status="unable_to_check",
            profile_url="",
            profile=profile,
            search=search,
            match=match,
            shop_fetch=shop_fetch,
            detection=detection,
            summary="No TikTok profile URL in sheet",
        )

    profile, profile_fetch = fetch_profile(profile_url)
    search_name = profile.get("profile_name") or sheet_shop_name or profile.get("handle") or ""

    if not search_name:
        return _result(
            voucher_status="unable_to_check",
            profile_url=profile_url,
            profile=profile,
            search={"search_query": "", "search_results_count": 0, "blocked": False},
            match=None,
            shop_fetch=profile_fetch,
            detection=detection,
            summary="Could not extract profile name from TikTok profile page",
        )

    extra = build_profile_shop_candidates(profile)
    search = search_tiktok_shop(search_name, extra_candidates=extra)

    filtered: list[dict[str, Any]] = []
    for cand in list(search.get("candidates") or []):
        if cand.get("source") in ("handle_shop_path", "profile_shop_link"):
            probe = fetch_tiktok_page(cand.get("shop_url", ""))
            if not (probe.get("html_loaded") or len(probe.get("page_text") or "") > 100):
                continue
        filtered.append(cand)
    search["candidates"] = filtered
    search["search_results_count"] = len(filtered)

    if search.get("blocked") and search.get("search_results_count", 0) == 0:
        return _result(
            voucher_status="unable_to_check",
            profile_url=profile_url,
            profile=profile,
            search=search,
            match=None,
            shop_fetch={},
            detection=detection,
            summary="TikTok Shop search blocked or unavailable on web",
        )

    match = pick_best_shop_match(profile, sheet_shop_name, search.get("candidates") or [])

    if not match:
        return _result(
            voucher_status="shop_not_found",
            profile_url=profile_url,
            profile=profile,
            search=search,
            match=None,
            shop_fetch={},
            detection=detection,
            summary=(
                f"Profile name '{search_name}' extracted but no matching TikTok Shop "
                f"({search.get('search_results_count', 0)} raw results)"
            ),
        )

    shop_url = match.get("shop_url") or ""
    shop_fetch = fetch_tiktok_page(shop_url)
    shop_fetch = enrich_fetch_with_access(shop_fetch)

    detection = detect_voucher_signals(
        shop_fetch.get("page_text") or "",
        html=shop_fetch.get("html") or "",
        dom_snippets=shop_fetch.get("dom_snippets"),
    )
    voucher_status = resolve_voucher_status(shop_fetch, detection)

    summary_parts = [
        f"Profile: {search_name}",
        f"Matched shop: {match.get('shop_name')} ({match.get('match_confidence')})",
        f"Voucher: {voucher_status.replace('_', ' ')}",
    ]
    if detection.get("voucher_text"):
        summary_parts.append(detection["voucher_text"][:80])

    return _result(
        voucher_status=voucher_status,
        profile_url=profile_url,
        profile=profile,
        search=search,
        match=match,
        shop_fetch=shop_fetch,
        detection=detection,
        summary=" | ".join(summary_parts),
    )


def _result(
    *,
    voucher_status: str,
    profile_url: str,
    profile: dict[str, Any],
    search: dict[str, Any],
    match: dict[str, Any] | None,
    shop_fetch: dict[str, Any],
    detection: dict[str, Any],
    summary: str,
) -> dict[str, Any]:
    check_reason = public_pipeline_check_reason(
        profile_url=profile_url,
        profile=profile,
        search=search,
        match=match,
        shop_fetch=shop_fetch,
        detection=detection,
        voucher_status=voucher_status,
        summary=summary,
    )
    return {
        "voucher_status": voucher_status,
        "voucher_text": detection.get("voucher_text") or "",
        "check_reason": check_reason,
        "check_summary": summary,
        "profile_name_extracted": profile.get("profile_name") or "",
        "matched_shop_name": (match or {}).get("shop_name") or "",
        "tiktok_shop_url": (match or {}).get("shop_url") or "",
        "match_confidence": (match or {}).get("match_confidence") or "",
    }
