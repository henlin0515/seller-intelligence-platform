from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from seller.competitor_tracker.fetcher import fetch_tiktok_page
from seller.competitor_tracker.utils import (
    deep_find_keys,
    extract_handle_from_url,
    parse_json_blobs_from_html,
    safe_http_url,
)

_SHOP_LINK_RE = re.compile(
    r'https?://(?:www\.)?tiktok\.com/[^"\s]*(?:/shop|view/shop|store)[^"\s]*|'
    r'https?://shop\.tiktok\.com/[^"\s]+',
    re.I,
)


def _parse_og_meta(soup: BeautifulSoup) -> dict[str, str]:
    meta: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        prop = tag.get("property") or tag.get("name") or ""
        content = (tag.get("content") or "").strip()
        if prop and content:
            meta[prop.lower()] = content
    return meta


def _name_from_og_title(title: str) -> str:
    """e.g. 'Mumu PH (@mumuph) | TikTok' -> 'Mumu PH'."""
    if not title:
        return ""
    m = re.match(r"^(.+?)\s*\(@", title)
    if m:
        return m.group(1).strip()
    return title.split("|")[0].strip()


def _extract_from_json_blobs(html: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    shop_urls: list[str] = []
    for blob in parse_json_blobs_from_html(html):
        for raw_url in deep_find_keys(
            blob,
            ("storeUrl", "shopLink", "shop_url", "sellerLink", "showcaseUrl"),
        ):
            if isinstance(raw_url, str) and ("shop" in raw_url.lower() or "store" in raw_url.lower()):
                shop_urls.append(safe_http_url(raw_url))
        for nick in deep_find_keys(blob, ("nickName", "nickname")):
            if isinstance(nick, str) and len(nick.strip()) > 1:
                out.setdefault("profile_name", nick.strip())
                break
        for uid in deep_find_keys(blob, ("uniqueId",)):
            if isinstance(uid, str) and uid.strip():
                out.setdefault("handle", uid.strip().lstrip("@"))
                break
        for sig in deep_find_keys(blob, ("signature", "bio", "desc")):
            if isinstance(sig, str) and sig:
                out.setdefault("bio", sig[:500])
        for fc in deep_find_keys(blob, ("followerCount", "follower_count", "fans")):
            if isinstance(fc, (int, float, str)) and fc:
                out.setdefault("followers", str(fc))
        for link in deep_find_keys(blob, ("bioLink", "bio_link", "externalUrl")):
            if isinstance(link, str) and link.startswith("http"):
                out.setdefault("external_links", []).append(link)
    if "external_links" in out:
        out["external_links"] = list(dict.fromkeys(out["external_links"]))[:5]
    if shop_urls:
        out["shop_urls_from_json"] = list(dict.fromkeys(shop_urls))[:8]
    return out


def extract_shop_links_from_html(html: str) -> list[str]:
    links = list(dict.fromkeys(_SHOP_LINK_RE.findall(html or "")))
    return [safe_http_url(u) for u in links if u][:5]


def parse_profile_from_fetch(fetch: dict[str, Any], profile_url: str) -> dict[str, Any]:
    html = fetch.get("html") or ""
    handle = extract_handle_from_url(profile_url) or extract_handle_from_url(fetch.get("final_url") or "")
    soup = BeautifulSoup(html, "html.parser") if html else None
    meta = _parse_og_meta(soup) if soup else {}
    og_title = meta.get("og:title", "") or fetch.get("page_title") or ""
    profile_name = _name_from_og_title(og_title)

    json_bits = _extract_from_json_blobs(html)
    if json_bits.get("profile_name"):
        profile_name = json_bits["profile_name"]
    if json_bits.get("handle"):
        handle = json_bits["handle"]
    if not profile_name and handle:
        profile_name = handle

    external_links: list[str] = list(json_bits.get("external_links") or [])
    for a in (soup.find_all("a", href=True) if soup else []):
        href = safe_http_url(a.get("href", ""))
        if href and href.startswith("http") and "tiktok.com" not in href:
            external_links.append(href)
    external_links = list(dict.fromkeys(external_links))[:5]

    shop_links = list(
        dict.fromkeys(
            extract_shop_links_from_html(html) + list(json_bits.get("shop_urls_from_json") or [])
        )
    )[:8]
    handle = (handle or json_bits.get("handle") or "").strip()
    if handle:
        shop_links.append(f"https://www.tiktok.com/@{handle}/shop")

    return {
        "profile_url": profile_url,
        "profile_name": (profile_name or "").strip(),
        "handle": (handle or "").strip(),
        "followers": json_bits.get("followers"),
        "bio": json_bits.get("bio"),
        "external_links": external_links,
        "shop_links_on_profile": shop_links,
        "page_title": og_title or fetch.get("page_title"),
    }


def fetch_profile(profile_url: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load profile page and return (profile_info, raw_fetch)."""
    fetch = fetch_tiktok_page(profile_url)
    profile = parse_profile_from_fetch(fetch, profile_url)
    return profile, fetch
