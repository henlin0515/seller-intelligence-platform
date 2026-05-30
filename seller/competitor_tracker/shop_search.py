from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from seller.competitor_tracker.fetcher import fetch_tiktok_page
from seller.competitor_tracker.page_analysis import analyze_access_signals
from seller.competitor_tracker.utils import parse_json_blobs_from_html, safe_http_url

logger = logging.getLogger("seller.competitor_tracker.shop_search")

_SHOP_HREF_RE = re.compile(
    r"(/view/shop/[^\"'\s]+|/shop/store/[^\"'\s]+|@[^/\"'\s]+/shop|shop\.tiktok\.com/[^\"'\s]+)",
    re.I,
)


def build_search_urls(query: str) -> list[str]:
    q = quote_plus(query.strip())
    return [
        f"https://www.tiktok.com/search?q={q}",
        f"https://www.tiktok.com/search/user?q={q}",
    ]


def _parse_candidates_from_html(html: str, base_url: str = "https://www.tiktok.com") -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    if not html:
        return candidates

    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = safe_http_url(a.get("href", ""))
        if not href:
            continue
        if not _looks_like_shop_url(href):
            continue
        full = urljoin(base_url, href) if href.startswith("/") else href
        if full in seen_urls:
            continue
        seen_urls.add(full)
        name = (a.get_text(" ", strip=True) or "").strip()
        if not name or len(name) > 120:
            name = _shop_name_from_url(full)
        candidates.append(
            {
                "shop_name": name,
                "shop_url": full,
                "avatar_url": "",
                "source": "html_link",
            }
        )

    for blob in parse_json_blobs_from_html(html):
        _walk_json_for_shops(blob, candidates, seen_urls)

    for m in _SHOP_HREF_RE.finditer(html):
        path = m.group(1)
        full = urljoin(base_url, path) if path.startswith("/") else f"https://{path}"
        if full not in seen_urls and _looks_like_shop_url(full):
            seen_urls.add(full)
            candidates.append(
                {
                    "shop_name": _shop_name_from_url(full),
                    "shop_url": full,
                    "avatar_url": "",
                    "source": "html_regex",
                }
            )

    return candidates[:30]


def _walk_json_for_shops(obj: Any, out: list[dict[str, Any]], seen: set[str], depth: int = 0) -> None:
    if depth > 14:
        return
    if isinstance(obj, dict):
        name = (
            obj.get("storeName")
            or obj.get("shop_name")
            or obj.get("seller_name")
            or obj.get("title")
            or obj.get("nickname")
            or obj.get("nickName")
        )
        url = (
            obj.get("shop_url")
            or obj.get("store_url")
            or obj.get("shopLink")
            or obj.get("link")
        )
        if isinstance(name, str) and isinstance(url, str) and _looks_like_shop_url(url):
            full = safe_http_url(url)
            if full not in seen:
                seen.add(full)
                out.append(
                    {
                        "shop_name": name[:120],
                        "shop_url": full,
                        "avatar_url": (obj.get("avatar") or obj.get("avatarThumb") or "")[:500],
                        "source": "json",
                    }
                )
        for v in obj.values():
            _walk_json_for_shops(v, out, seen, depth + 1)
    elif isinstance(obj, list):
        for item in obj[:60]:
            _walk_json_for_shops(item, out, seen, depth + 1)


def _looks_like_shop_url(url: str) -> bool:
    u = (url or "").lower()
    if not u.startswith("http"):
        return False
    markers = ("/shop", "shop.tiktok", "view/shop", "/store", "ec/store", "seller")
    return any(m in u for m in markers)


def _shop_name_from_url(url: str) -> str:
    path = url.split("?")[0].rstrip("/")
    part = path.split("/")[-1]
    return part.replace("-", " ").replace("_", " ")[:80] or "TikTok Shop"


def build_profile_shop_candidates(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Candidates from profile page (shop tab links, @handle/shop)."""
    name = profile.get("profile_name") or profile.get("handle") or "TikTok Shop"
    handle = profile.get("handle") or ""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for url in profile.get("shop_links_on_profile") or []:
        if url and url not in seen:
            seen.add(url)
            out.append(
                {
                    "shop_name": name,
                    "shop_url": url,
                    "avatar_url": profile.get("avatar_url") or "",
                    "source": "profile_shop_link",
                }
            )
    if handle:
        constructed = f"https://www.tiktok.com/@{handle}/shop"
        if constructed not in seen:
            seen.add(constructed)
            out.append(
                {
                    "shop_name": name,
                    "shop_url": constructed,
                    "avatar_url": profile.get("avatar_url") or "",
                    "source": "handle_shop_path",
                }
            )
    return out


def search_tiktok_shop(query: str, *, extra_candidates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """
    Search TikTok for shops matching profile name.
    Returns candidates, blocked flag, search metadata.
    """
    query = (query or "").strip()
    if not query:
        return {
            "ok": False,
            "blocked": False,
            "search_query": "",
            "search_results_count": 0,
            "candidates": [],
            "error": "empty_query",
        }

    all_candidates: list[dict[str, Any]] = list(extra_candidates or [])
    seen: set[str] = {c.get("shop_url", "") for c in all_candidates}
    blocked = False
    last_fetch: dict[str, Any] = {}

    for search_url in build_search_urls(query):
        fetch = fetch_tiktok_page(search_url)
        last_fetch = fetch
        access = analyze_access_signals(
            fetch.get("page_text") or "",
            fetch.get("page_title") or "",
            fetch.get("http_status"),
        )
        if access.get("tiktok_blocked"):
            blocked = True

        parsed = _parse_candidates_from_html(fetch.get("html") or "", fetch.get("final_url") or search_url)
        for c in parsed:
            u = c.get("shop_url", "")
            if u and u not in seen:
                seen.add(u)
                all_candidates.append(c)

        if len(all_candidates) >= 5:
            break

    return {
        "ok": not blocked or len(all_candidates) > 0,
        "blocked": blocked and len(all_candidates) == 0,
        "search_query": query,
        "search_results_count": len(all_candidates),
        "candidates": all_candidates,
        "error": last_fetch.get("fetch_error"),
        "last_search_url": last_fetch.get("final_url"),
    }
