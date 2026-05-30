from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.exceptions import InvalidSchema, MissingSchema

from seller.competitor_tracker.constants import FETCH_TIMEOUT_SEC

logger = logging.getLogger("seller.competitor_tracker.fetcher")

_SESSION = requests.Session()
_SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-PH,en;q=0.9,fil;q=0.8,zh-CN;q=0.7,zh-TW;q=0.6",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
)

_CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]


def _is_railway_or_container() -> bool:
    return bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_SERVICE_ID")
        or os.getenv("RAILWAY_PROJECT_ID")
    )


def _headless() -> bool:
    return os.getenv("HEADLESS", "0") == "1" or _is_railway_or_container()


def fetch_tiktok_page(url: str) -> dict[str, Any]:
    """
    Fetch TikTok shop page text. Tries HTTP first, optional Playwright fallback.
    Never raises — returns ok=False with error message for logging.
    """
    url = (url or "").strip()
    if not url:
        return {"ok": False, "error": "empty_url", "page_text": ""}

    http_result = _fetch_http(url)
    if http_result["ok"] and len(http_result.get("page_text", "")) >= 800:
        return http_result

    pw_result = _fetch_playwright(url)
    if pw_result["ok"] and len(pw_result.get("page_text", "")) > len(http_result.get("page_text", "")):
        return pw_result

    if http_result["ok"]:
        return http_result
    if pw_result["ok"]:
        return pw_result

    return {
        "ok": False,
        "error": pw_result.get("error") or http_result.get("error") or "fetch_failed",
        "page_text": "",
    }


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https")


def _fetch_http(url: str) -> dict[str, Any]:
    try:
        current = url
        resp = None
        for _ in range(12):
            if not _is_http_url(current):
                return {"ok": False, "error": "non_http_redirect", "page_text": ""}
            resp = _SESSION.get(current, timeout=FETCH_TIMEOUT_SEC, allow_redirects=False)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = (resp.headers.get("Location") or "").strip()
                if not location:
                    return {"ok": False, "error": "redirect_no_location", "page_text": ""}
                next_url = urljoin(current, location)
                if not _is_http_url(next_url):
                    return {"ok": False, "error": "app_scheme_redirect", "page_text": ""}
                current = next_url
                continue
            break

        if resp is None:
            return {"ok": False, "error": "no_response", "page_text": ""}
        if resp.status_code >= 400:
            return {"ok": False, "error": f"http_{resp.status_code}", "page_text": ""}
        html = resp.text or ""
        soup = BeautifulSoup(html, "html.parser")
        visible = soup.get_text(" ", strip=True)
        from seller.competitor_tracker.detector import _normalize_page_text

        page_text = _normalize_page_text(html, visible)
        if len(page_text) < 100:
            return {"ok": False, "error": "empty_body", "page_text": page_text}
        return {"ok": True, "error": None, "page_text": page_text, "method": "http"}
    except (InvalidSchema, MissingSchema):
        logger.warning("TikTok redirect to non-HTTP scheme: %s", url[:80])
        return {"ok": False, "error": "invalid_redirect_scheme", "page_text": ""}
    except requests.Timeout:
        logger.warning("TikTok HTTP timeout: %s", url[:80])
        return {"ok": False, "error": "timeout", "page_text": ""}
    except requests.RequestException as exc:
        logger.warning("TikTok HTTP error for %s: %s", url[:80], exc)
        return {"ok": False, "error": "request_error", "page_text": ""}
    except Exception as exc:
        logger.warning("TikTok HTTP unexpected error: %s", exc)
        return {"ok": False, "error": "unexpected", "page_text": ""}


def _fetch_playwright(url: str) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "error": "playwright_missing", "page_text": ""}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=_headless(), args=_CHROMIUM_ARGS)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=int(FETCH_TIMEOUT_SEC * 1000))
                page.wait_for_timeout(2500)
                html = page.content()
                visible = page.inner_text("body")
            finally:
                browser.close()

        from seller.competitor_tracker.detector import _normalize_page_text

        page_text = _normalize_page_text(html, visible)
        if len(page_text) < 100:
            return {"ok": False, "error": "empty_body_pw", "page_text": page_text}
        return {"ok": True, "error": None, "page_text": page_text, "method": "playwright"}
    except Exception as exc:
        logger.warning("TikTok Playwright error for %s: %s", url[:80], exc)
        return {"ok": False, "error": "playwright_error", "page_text": ""}
