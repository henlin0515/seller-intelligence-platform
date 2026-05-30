"""
HTTP fallback for Seller Education research when Playwright is unavailable.

Uses requests + BeautifulSoup only (no browser binaries).
"""

from __future__ import annotations

import logging
import re
import time
from copy import deepcopy
from urllib.parse import quote_plus, urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "HTTP fallback requires beautifulsoup4 and requests. "
        "Install requirements.txt on the server."
    ) from exc

from program_dictionary import expand_search_keywords
from query_mode import resolve_search_plan
from search import (
    DEFAULT_MAX_SOURCES,
    EDU_HOME,
    EDU_HUB_SECTIONS,
    FETCH_TIMEOUT_MS,
    SEARCH_TIMEOUT_MS,
    _debug,
    _infer_source_type,
    _is_edu_content_url,
    _normalize_text,
    _prepare_source_for_claude,
    _score_relevance,
)


def _merge_ranked_links(
    ranked: dict[str, tuple[int, str, str]],
    entries: list[tuple[int, str, str]],
) -> None:
    for score, title, url in entries:
        if url not in ranked or score > ranked[url][0]:
            ranked[url] = (score, title, url)

logger = logging.getLogger("edu_http_fallback")

_SESSION = requests.Session()
_SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (compatible; ShopeeSellerEduBot/1.0; +https://seller.shopee.ph/edu)"
        ),
        "Accept-Language": "en-PH,en;q=0.9,zh-TW;q=0.8",
    }
)


def _fetch_html(url: str, timeout_sec: float) -> str:
    resp = _SESSION.get(url, timeout=timeout_sec)
    resp.raise_for_status()
    resp.encoding = resp.encoding or "utf-8"
    return resp.text


def _parse_edu_links(html: str, limit: int = 50) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        url = urljoin(EDU_HOME, href)
        if not _is_edu_content_url(url) or url in seen:
            continue
        title = _normalize_text(a.get_text(" ", strip=True))
        if len(title) < 3:
            continue
        seen.add(url)
        out.append((title, url))
        if len(out) >= limit:
            break
    return out


def _extract_article_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body
    if not main:
        return _normalize_text(soup.get_text("\n", strip=True))
    return _normalize_text(main.get_text("\n", strip=True))


def _fetch_article(url: str, fallback_title: str, timeout_sec: float) -> dict | None:
    try:
        html = _fetch_html(url, timeout_sec)
    except Exception as exc:
        _debug(f"http fetch failed {url}: {exc}")
        return None

    soup = BeautifulSoup(html, "html.parser")
    title = fallback_title
    for tag in ("h1", "h2"):
        el = soup.find(tag)
        if el:
            parsed = _normalize_text(el.get_text(" ", strip=True))
            if parsed:
                title = parsed
                break
    if not title or title == fallback_title:
        if soup.title and soup.title.string:
            title = soup.title.string.split("|")[0].strip() or fallback_title

    content = _extract_article_text(html)
    if not content.strip():
        return None

    return {
        "title": title,
        "url": url,
        "content": content,
        "source_type": _infer_source_type(url, title),
    }


def search_edu_articles_http(
    question: str,
    keywords: list[str],
    plan: dict | None = None,
) -> tuple[list[dict], bool]:
    """Sync HTTP-only research (Playwright fallback)."""
    if plan is None:
        plan = resolve_search_plan(question)

    max_sources = plan.get("max_sources", DEFAULT_MAX_SOURCES)
    full_content = plan.get("full_content", False)
    fast = plan.get("fast", True)
    search_keywords = expand_search_keywords(keywords, question)
    fetch_timeout = FETCH_TIMEOUT_MS / 1000
    search_deadline = time.monotonic() + (SEARCH_TIMEOUT_MS / 1000)

    ranked: dict[str, tuple[int, str, str]] = {}

    query_limit = 5 if fast else 8
    queries: list[str] = []
    for keyword in search_keywords[:query_limit]:
        if isinstance(keyword, str) and keyword.strip():
            queries.append(keyword.strip())
    if question.strip() and question.strip() not in queries:
        queries.append(question.strip())

    for query in queries:
        if time.monotonic() >= search_deadline:
            break
        search_urls = [
            f"{EDU_HOME}/search?keyword={quote_plus(query)}",
            f"{EDU_HOME}/search?q={quote_plus(query)}",
        ]
        for search_url in search_urls:
            try:
                html = _fetch_html(search_url, min(fetch_timeout, 8.0))
                batch = []
                for title, url in _parse_edu_links(html, limit=30):
                    score = _score_relevance(question, title, "", search_keywords)
                    batch.append((score, title, url))
                _merge_ranked_links(ranked, batch)
                if batch:
                    break
            except Exception as exc:
                _debug(f"http search failed {search_url}: {exc}")

    for section_url in EDU_HUB_SECTIONS:
        if time.monotonic() >= search_deadline:
            break
        try:
            html = _fetch_html(section_url, min(fetch_timeout, 10.0))
            batch = []
            for title, url in _parse_edu_links(html, limit=40):
                score = _score_relevance(question, title, "", search_keywords)
                if score > 0:
                    batch.append((score, title, url))
            _merge_ranked_links(ranked, batch)
        except Exception as exc:
            _debug(f"http hub browse failed {section_url}: {exc}")

    ranked_list = sorted(ranked.values(), key=lambda x: x[0], reverse=True)
    if not ranked_list:
        logger.warning("HTTP fallback found no education links for: %s", question[:80])
        return [], False

    sources: list[dict] = []
    best_score = 0
    for _, title, url in ranked_list[:max_sources]:
        raw = _fetch_article(url, title, fetch_timeout)
        if not raw:
            continue
        prepared = _prepare_source_for_claude(
            raw, question, search_keywords, full_content=full_content
        )
        full_score = _score_relevance(
            question,
            prepared["title"],
            raw.get("content", ""),
            search_keywords,
        )
        prepared["score"] = full_score
        sources.append(prepared)
        best_score = max(best_score, full_score)

    sources.sort(key=lambda s: s.get("score", 0), reverse=True)
    for s in sources:
        s.pop("score", None)

    question_words = [w for w in re.findall(r"[a-z0-9]+", question.lower()) if len(w) > 3]
    strong_match = False
    if sources and question_words:
        combined_text = " ".join(
            f"{s.get('title', '')} {s.get('content', '')}" for s in sources[:3]
        ).lower()
        hits = sum(1 for w in question_words if w in combined_text)
        strong_match = hits >= max(2, len(question_words) // 3) and best_score >= 3

    logger.info("HTTP fallback returned %s sources (strong_match=%s)", len(sources), strong_match)
    return sources, strong_match
