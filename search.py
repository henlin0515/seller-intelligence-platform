"""
Seller Education research via Playwright.

Uses async_playwright only — do not import playwright.sync_api or sync_playwright.
Falls back to HTTP crawler when Chromium is unavailable (e.g. Railway misbuild).
"""
import asyncio
import logging
import os
import re
import time
from copy import deepcopy
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from program_dictionary import expand_search_keywords, relevance_phrases
from query_mode import resolve_search_plan

load_dotenv()

logger = logging.getLogger("search")

EDU_HOME = "https://seller.shopee.ph/edu"
EDU_HUB_SECTIONS = (
    "https://seller.shopee.ph/edu/articles",
    "https://seller.shopee.ph/edu/courses",
    "https://seller.shopee.ph/edu/webinars",
)
def _is_railway_or_container() -> bool:
    return bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_SERVICE_ID")
        or os.getenv("RAILWAY_PROJECT_ID")
    )


HEADLESS = os.getenv("HEADLESS", "0") == "1" or _is_railway_or_container()

CHROMIUM_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]
DEBUG = os.getenv("DEBUG", "0") == "1"
DEFAULT_MAX_SOURCES = int(os.getenv("MAX_SOURCES", "5"))
SEARCH_TIMEOUT_MS = int(os.getenv("SEARCH_TIMEOUT_MS", "10000"))
FETCH_TIMEOUT_MS = int(os.getenv("FETCH_TIMEOUT_MS", "10000"))
EXCERPT_MAX_CHARS = int(os.getenv("EXCERPT_MAX_CHARS", "4500"))

MAX_LINK_CANDIDATES = 40
SEARCH_WAIT_MS = 1200
SCROLL_PAUSE_MS = 400
SCROLL_STABLE_ROUNDS_FAST = 2
SCROLL_STABLE_ROUNDS_FULL = 3
MAX_SCROLL_ATTEMPTS_FAST = 12
MAX_SCROLL_ATTEMPTS_FULL = 25

SKIP_PATH_SUFFIXES = (
    "/edu/home",
    "/edu/login",
    "/edu/search",
)

_ARTICLE_CACHE: dict[str, dict] = {}


def _debug(message: str) -> None:
    if DEBUG:
        print(f"[debug] {message}")


def _print_source_debug(source: dict) -> None:
    if not DEBUG:
        return
    print("[DEBUG]")
    print(f"Article Title: {source.get('title', 'Untitled')}")
    print(f"URL: {source.get('url', '')}")
    print(f"Source Type: {source.get('source_type', 'unknown')}")
    print(f"Character Count: {len(source.get('content', ''))}")
    if source.get("excerpt"):
        print(f"(excerpt from {source.get('full_length', '?')} chars)")
    print()


def _past_deadline(deadline: float) -> bool:
    return time.monotonic() >= deadline


async def _dismiss_popups(page) -> None:
    for label in ("OK", "Close", "Cancel"):
        try:
            btn = page.get_by_role("button", name=label)
            if await btn.count() > 0:
                await btn.first.click(timeout=800)
                await asyncio.sleep(0.2)
        except Exception:
            pass


def _normalize_path(url: str) -> str:
    return urlparse(url).path.lower().rstrip("/")


def _is_edu_content_url(url: str) -> bool:
    if "seller.shopee.ph" not in url or "/edu" not in url:
        return False
    path = _normalize_path(url)
    if path in ("/edu", ""):
        return False
    if any(path == suffix.rstrip("/") or path.endswith(suffix) for suffix in SKIP_PATH_SUFFIXES):
        return False
    parts = [p for p in path.split("/") if p]
    return len(parts) >= 3


def _infer_source_type(url: str, title: str) -> str:
    blob = f"{_normalize_path(url)} {title.lower()}"
    rules = (
        ("webinar", "webinar"),
        ("course", "course"),
        ("announcement", "announcement"),
        ("faq", "faq"),
        ("policy", "policy"),
        ("guide", "guide"),
        ("help", "guide"),
        ("article", "article"),
    )
    for needle, kind in rules:
        if needle in blob:
            return kind
    return "article"


def _question_terms(question: str, keywords: list[str]) -> list[str]:
    terms: set[str] = set()
    for text in [question, *keywords]:
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            if len(word) > 2:
                terms.add(word)
    return list(terms)


def _score_relevance(question: str, title: str, content: str, keywords: list[str]) -> int:
    text = f"{title} {content}".lower()
    title_lower = title.lower()
    terms = _question_terms(question, keywords)
    phrases = relevance_phrases(question, keywords)

    hits = sum(1 for term in terms if term in text)
    title_bonus = sum(2 for term in terms if term in title_lower)
    phrase_hits = sum(3 for phrase in phrases if phrase.lower() in text)
    title_phrase_bonus = sum(4 for phrase in phrases if phrase.lower() in title_lower)
    return hits + title_bonus + phrase_hits + title_phrase_bonus


async def _scroll_until_stable(page, fast: bool) -> None:
    max_attempts = MAX_SCROLL_ATTEMPTS_FAST if fast else MAX_SCROLL_ATTEMPTS_FULL
    stable_target = SCROLL_STABLE_ROUNDS_FAST if fast else SCROLL_STABLE_ROUNDS_FULL
    prev_height = -1
    stable_rounds = 0
    attempts = 0

    while attempts < max_attempts and stable_rounds < stable_target:
        await page.evaluate(
            "() => window.scrollTo(0, Math.max(document.body.scrollHeight, document.documentElement.scrollHeight))"
        )
        await page.wait_for_timeout(SCROLL_PAUSE_MS)
        height = await page.evaluate(
            "() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
        )
        if height == prev_height:
            stable_rounds += 1
        else:
            stable_rounds = 0
        prev_height = height
        attempts += 1

    await page.wait_for_timeout(600 if fast else 1000)


def _normalize_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.strip())


async def _extract_readable_text(page, timeout_ms: int) -> str:
    candidates: list[str] = []
    selectors = (
        "article",
        "main",
        '[class*="article-detail"]',
        '[class*="article"]',
        '[class*="content"]',
    )
    per_block_timeout = min(5000, timeout_ms)

    for sel in selectors:
        try:
            blocks = page.locator(sel)
            block_count = await blocks.count()
            for i in range(min(block_count, 5)):
                try:
                    text = (await blocks.nth(i).inner_text(timeout=per_block_timeout) or "").strip()
                    if len(text) > 100:
                        candidates.append(text)
                except Exception:
                    continue
        except Exception:
            continue

    if not candidates:
        try:
            body = (await page.locator("body").inner_text(timeout=timeout_ms) or "").strip()
            if body:
                candidates.append(body)
        except Exception:
            pass

    if not candidates:
        return ""
    return _normalize_text(max(candidates, key=len))


def _extract_relevant_excerpt(
    full_text: str,
    question: str,
    keywords: list[str],
    max_chars: int = EXCERPT_MAX_CHARS,
) -> str:
    if len(full_text) <= max_chars:
        return full_text

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", full_text) if p.strip()]
    if not paragraphs:
        return full_text[:max_chars]

    terms = set(_question_terms(question, keywords))
    for phrase in relevance_phrases(question, keywords):
        for word in phrase.lower().split():
            if len(word) > 2:
                terms.add(word)

    scored: list[tuple[int, int, str]] = []
    for idx, para in enumerate(paragraphs):
        lower = para.lower()
        score = sum(2 if t in lower else 0 for t in terms)
        if idx == 0:
            score += 1
        scored.append((score, idx, para))

    scored.sort(key=lambda x: (-x[0], x[1]))
    chosen_indices: set[int] = set()
    parts: list[tuple[int, str]] = []
    total = 0

    for _, idx, para in scored:
        if total >= max_chars:
            break
        if idx in chosen_indices:
            continue
        block_indices = sorted({idx, idx - 1, idx + 1} & set(range(len(paragraphs))))
        for bi in block_indices:
            if bi in chosen_indices:
                continue
            chunk = paragraphs[bi]
            if total + len(chunk) + 2 > max_chars and total > 0:
                continue
            chosen_indices.add(bi)
            parts.append((bi, chunk))
            total += len(chunk) + 2

    if not parts:
        return full_text[:max_chars]

    parts.sort(key=lambda x: x[0])
    excerpt = "\n\n".join(p for _, p in parts)
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars]
    return excerpt


async def _fetch_source_full(
    page,
    url: str,
    fallback_title: str,
    fast: bool,
) -> dict:
    await page.goto(url, wait_until="domcontentloaded", timeout=FETCH_TIMEOUT_MS)
    await page.wait_for_timeout(800 if fast else 1200)
    await _dismiss_popups(page)

    title = fallback_title
    for sel in ("h1", "h2"):
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                parsed = (await el.inner_text(timeout=2000) or "").strip()
                if parsed:
                    title = parsed
                    break
        except Exception:
            pass
    if not title:
        page_title = await page.title()
        title = (page_title or "Untitled").split("|")[0].strip()

    await _scroll_until_stable(page, fast=fast)
    content = await _extract_readable_text(page, FETCH_TIMEOUT_MS)

    return {
        "title": title,
        "url": url,
        "content": content,
        "source_type": _infer_source_type(url, title),
    }


async def _get_source(
    page,
    url: str,
    fallback_title: str,
    fast: bool,
) -> dict | None:
    if url in _ARTICLE_CACHE:
        _debug(f"cache hit: {url}")
        return deepcopy(_ARTICLE_CACHE[url])

    try:
        source = await _fetch_source_full(page, url, fallback_title, fast=fast)
        if not source.get("content", "").strip():
            return None
        _ARTICLE_CACHE[url] = deepcopy(source)
        return source
    except PlaywrightTimeout:
        _debug(f"fetch timeout: {url}")
        return None
    except Exception as exc:
        _debug(f"fetch failed {url}: {exc}")
        return None


def _prepare_source_for_claude(
    source: dict,
    question: str,
    keywords: list[str],
    full_content: bool,
) -> dict:
    full_text = source.get("content", "")
    if full_content or len(full_text) <= EXCERPT_MAX_CHARS:
        out = deepcopy(source)
        out["excerpt"] = False
        out["full_length"] = len(full_text)
        return out

    excerpt = _extract_relevant_excerpt(full_text, question, keywords)
    out = deepcopy(source)
    out["content"] = excerpt
    out["excerpt"] = True
    out["full_length"] = len(full_text)
    return out


async def _collect_edu_links(page, limit: int = 50, fast: bool = False) -> list[tuple[str, str]]:
    seen: set[str] = set()
    results: list[tuple[str, str]] = []

    if not fast:
        await _scroll_until_stable(page, fast=True)

    anchors = page.locator("a[href*='/edu/']")
    count = min(await anchors.count(), limit)
    for i in range(count):
        link = anchors.nth(i)
        try:
            href = await link.get_attribute("href") or ""
            if not href:
                continue
            url = urljoin(EDU_HOME, href)
            if not _is_edu_content_url(url) or url in seen:
                continue
            title = (await link.inner_text(timeout=500) or "").strip()
            if not title or len(title) < 3:
                continue
            seen.add(url)
            results.append((title, url))
        except Exception:
            continue
    return results


async def _search_query(page, query: str, fast: bool) -> list[tuple[str, str]]:
    _debug(f"searching keyword: {query}")
    await page.goto(EDU_HOME, wait_until="domcontentloaded", timeout=SEARCH_TIMEOUT_MS)
    await page.wait_for_timeout(600)
    await _dismiss_popups(page)

    search = page.get_by_placeholder("Search")
    if await search.count() == 0:
        search = page.locator('input[type="search"], input[placeholder*="Search"]')
    await search.first.click()
    await search.first.fill(query)
    await search.first.press("Enter")
    await page.wait_for_timeout(SEARCH_WAIT_MS)
    await _dismiss_popups(page)

    return await _collect_edu_links(page, fast=fast)


async def _browse_hub_sections(
    page,
    question: str,
    keywords: list[str],
    deadline: float,
) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    seen: set[str] = set()

    for section_url in EDU_HUB_SECTIONS:
        if _past_deadline(deadline):
            _debug("hub browse stopped (search time budget)")
            break
        _debug(f"browsing hub: {section_url}")
        try:
            await page.goto(section_url, wait_until="domcontentloaded", timeout=SEARCH_TIMEOUT_MS)
            await page.wait_for_timeout(800)
            await _dismiss_popups(page)
            for title, url in await _collect_edu_links(page, limit=35, fast=True):
                if url in seen:
                    continue
                seen.add(url)
                score = _score_relevance(question, title, "", keywords)
                if score > 0:
                    found.append((score, title, url))
        except PlaywrightTimeout:
            _debug(f"timeout browsing: {section_url}")
        except Exception as exc:
            _debug(f"hub browse failed {section_url}: {exc}")

    return found


def _merge_ranked_links(
    ranked: dict[str, tuple[int, str, str]],
    entries: list[tuple[int, str, str]],
) -> None:
    for score, title, url in entries:
        if url not in ranked or score > ranked[url][0]:
            ranked[url] = (score, title, url)


async def _search_edu_articles_async(
    question: str,
    keywords: list[str],
    plan: dict | None = None,
) -> tuple[list[dict], bool]:
    """
    Async Playwright research (runs inside a dedicated event loop).
    Returns (sources prepared for Claude, strong_match).
    """
    if plan is None:
        plan = resolve_search_plan(question)

    max_sources = plan.get("max_sources", DEFAULT_MAX_SOURCES)
    full_content = plan.get("full_content", False)
    fast = plan.get("fast", True)

    _debug(
        f"search plan: mode={plan.get('mode')} max_sources={max_sources} "
        f"full_content={full_content} fast={fast}"
    )

    search_keywords = expand_search_keywords(keywords, question)
    query_limit = 5 if fast else 8
    queries: list[str] = []
    for keyword in search_keywords[:query_limit]:
        if isinstance(keyword, str) and keyword.strip():
            queries.append(keyword.strip())
    if question.strip() and question.strip() not in queries:
        queries.append(question.strip())

    ranked: dict[str, tuple[int, str, str]] = {}
    search_deadline = time.monotonic() + (SEARCH_TIMEOUT_MS / 1000)

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=True if HEADLESS else False,
        args=CHROMIUM_LAUNCH_ARGS,
    )
    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        locale="en-PH",
    )
    context.set_default_timeout(SEARCH_TIMEOUT_MS)
    page = await context.new_page()

    try:
        for query in queries:
            if _past_deadline(search_deadline):
                _debug("keyword search stopped (search time budget)")
                break
            try:
                batch = []
                for title, url in await _search_query(page, query, fast=fast):
                    score = _score_relevance(question, title, "", search_keywords)
                    batch.append((score, title, url))
                _merge_ranked_links(ranked, batch)
            except PlaywrightTimeout:
                _debug(f"search timeout: {query}")
            except Exception as exc:
                _debug(f"search failed for '{query}': {exc}")

        if not fast:
            hub_links = await _browse_hub_sections(
                page, question, search_keywords, search_deadline
            )
            _merge_ranked_links(ranked, hub_links)

        ranked_list = sorted(ranked.values(), key=lambda x: x[0], reverse=True)
        if not ranked_list:
            _debug("no education sources found")
            return [], False

        top_links = ranked_list[:max_sources]
        _debug(
            f"ranked {len(ranked_list)} links; fetching top {len(top_links)} "
            f"(relevance filter)"
        )

        sources: list[dict] = []
        best_score = 0
        for _, title, url in top_links:
            raw = await _get_source(page, url, title, fast=fast)
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
            _print_source_debug(prepared)

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

        return sources, strong_match
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()


def chromium_executable_available() -> bool:
    """True when Playwright can resolve an on-disk Chromium binary."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            exe = p.chromium.executable_path
            return bool(exe and os.path.isfile(exe))
    except Exception as exc:
        logger.warning("Playwright Chromium check failed: %s", exc)
        return False


def _run_search_in_isolated_loop(
    question: str,
    keywords: list[str],
    plan: dict | None,
) -> tuple[list[dict], bool]:
    """
    Run async Playwright in a fresh event loop (worker thread).
    Avoids 'Sync API inside asyncio loop' when called from FastAPI/uvicorn.
    """
    return asyncio.run(_search_edu_articles_async(question, keywords, plan))


def _run_search_with_fallback(
    question: str,
    keywords: list[str],
    plan: dict | None,
) -> tuple[list[dict], bool]:
    """Playwright first; HTTP fallback on missing browser or runtime errors."""
    if chromium_executable_available():
        try:
            sources, strong = _run_search_in_isolated_loop(question, keywords, plan)
            if sources:
                logger.info("Playwright research returned %s sources", len(sources))
                return sources, strong
            logger.warning("Playwright returned no sources; trying HTTP fallback")
        except Exception as exc:
            logger.warning("Playwright research failed (%s); using HTTP fallback", exc)
    else:
        logger.warning(
            "Playwright Chromium not available; using HTTP fallback (requests + BeautifulSoup)"
        )

    from edu_http_fallback import search_edu_articles_http

    return search_edu_articles_http(question, keywords, plan)


async def search_edu_articles(
    question: str,
    keywords: list[str],
    plan: dict | None = None,
) -> tuple[list[dict], bool]:
    """
    Public async entry for FastAPI — awaits research in a dedicated thread + loop.
    Never raises: falls back to HTTP crawler so /chat always returns.
    """
    try:
        return await asyncio.to_thread(
            _run_search_with_fallback, question, keywords, plan
        )
    except Exception as exc:
        logger.exception("All research backends failed: %s", exc)
        return [], False
