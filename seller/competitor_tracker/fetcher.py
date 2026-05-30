from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.exceptions import InvalidSchema, MissingSchema

from seller.competitor_tracker.constants import FETCH_TIMEOUT_SEC
from seller.competitor_tracker.detector import _normalize_page_text

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

_PLAYWRIGHT_WAIT_MS = int(os.getenv("COMPETITOR_PW_WAIT_MS", "4500"))

_DOM_JS = """
() => {
  const hints = ['coupon', 'voucher', 'promo', 'promotion', 'discount', 'Voucher', 'Coupon'];
  const out = [];
  const seen = new Set();
  for (const hint of hints) {
    const nodes = document.querySelectorAll(
      `[class*="${hint}"], [data-e2e*="${hint}"], [aria-label*="${hint}" i]`
    );
    nodes.forEach(el => {
      const t = (el.innerText || '').trim();
      if (!t || t.length > 300 || seen.has(t)) return;
      if (/voucher|coupon|discount|off|₱|%|diskwento|優惠|折扣|免運|shipping|min\\.?\\s*spend/i.test(t)) {
        seen.add(t);
        out.push(t.slice(0, 220));
      }
    });
  }
  return [...out].slice(0, 12);
}
"""


def _is_railway_or_container() -> bool:
    return bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_SERVICE_ID")
        or os.getenv("RAILWAY_PROJECT_ID")
    )


def _headless() -> bool:
    return os.getenv("HEADLESS", "0") == "1" or _is_railway_or_container()


def chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            exe = p.chromium.executable_path
            return bool(exe and os.path.isfile(exe))
    except Exception:
        return False


def _is_http_url(url: str) -> bool:
    return urlparse(url).scheme in ("http", "https")


def _base_detail(start_url: str) -> dict[str, Any]:
    return {
        "ok": False,
        "start_url": start_url,
        "final_url": start_url,
        "http_status": None,
        "page_title": "",
        "html_loaded": False,
        "html_length": 0,
        "visible_text_length": 0,
        "page_text": "",
        "html": "",
        "redirect_chain": [start_url],
        "used_http": False,
        "used_playwright": False,
        "fetch_error": None,
        "dom_snippets": [],
        "tiktok_blocked": False,
        "login_required": False,
    }


def fetch_tiktok_page(url: str) -> dict[str, Any]:
    """
    Fetch TikTok shop with diagnostics. HTTP first, Playwright when needed for SPA/blocks.
    """
    url = (url or "").strip()
    if not url:
        d = _base_detail("")
        d["fetch_error"] = "empty_url"
        return d

    http = _fetch_http(url)
    http["used_http"] = http.get("attempted_http", True)

    thin_visible = http.get("visible_text_length", 0) < 500
    need_pw = chromium_available() and (
        not http.get("ok")
        or thin_visible
        or http.get("html_length", 0) < 1800
        or http.get("fetch_error") in ("app_scheme_redirect", "invalid_redirect_scheme", "empty_body")
        or "tiktok.com" in (url or "").lower()
        or "vt.tiktok" in (url or "").lower()
    )

    pw: dict[str, Any] | None = None
    if need_pw:
        pw = _fetch_playwright(url)
        pw["used_playwright"] = pw.get("attempted_playwright", True)

    merged = _merge_fetch_results(url, http, pw)
    return merged


def _merge_fetch_results(start_url: str, http: dict[str, Any], pw: dict[str, Any] | None) -> dict[str, Any]:
    candidates = [http]
    if pw:
        candidates.append(pw)

    best = max(candidates, key=lambda c: len(c.get("page_text") or ""))
    out = _base_detail(start_url)
    out.update(
        {
            "ok": best.get("ok", False),
            "final_url": best.get("final_url") or http.get("final_url") or start_url,
            "http_status": best.get("http_status") or http.get("http_status"),
            "page_title": best.get("page_title") or http.get("page_title") or "",
            "html_loaded": bool(best.get("html_loaded")),
            "html_length": int(best.get("html_length") or 0),
            "visible_text_length": int(best.get("visible_text_length") or 0),
            "page_text": best.get("page_text") or "",
            "html": (best.get("html") or "")[:500_000],
            "redirect_chain": best.get("redirect_chain") or http.get("redirect_chain") or [start_url],
            "used_http": bool(http.get("used_http")),
            "used_playwright": bool(pw and pw.get("used_playwright")),
            "fetch_error": best.get("fetch_error") or http.get("fetch_error"),
            "dom_snippets": list(
                dict.fromkeys((best.get("dom_snippets") or []) + (pw.get("dom_snippets") if pw else []))
            )[:12],
        }
    )
    if not out["ok"] and not out["html_loaded"]:
        out["fetch_error"] = out["fetch_error"] or "fetch_failed"
    elif out["html_loaded"]:
        out["ok"] = True
        out["fetch_error"] = None
    return out


def _fetch_http(url: str) -> dict[str, Any]:
    detail = _base_detail(url)
    detail["attempted_http"] = True
    detail["used_http"] = True
    try:
        current = url
        chain = [url]
        resp = None
        for _ in range(12):
            if not _is_http_url(current):
                detail["fetch_error"] = "non_http_redirect"
                detail["redirect_chain"] = chain
                return detail
            resp = _SESSION.get(current, timeout=FETCH_TIMEOUT_SEC, allow_redirects=False)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = (resp.headers.get("Location") or "").strip()
                if not location:
                    detail["fetch_error"] = "redirect_no_location"
                    detail["http_status"] = resp.status_code
                    return detail
                next_url = urljoin(current, location)
                if not _is_http_url(next_url):
                    detail["fetch_error"] = "app_scheme_redirect"
                    detail["http_status"] = resp.status_code
                    detail["final_url"] = current
                    detail["redirect_chain"] = chain
                    return detail
                current = next_url
                chain.append(current)
                continue
            break

        if resp is None:
            detail["fetch_error"] = "no_response"
            return detail

        detail["http_status"] = resp.status_code
        detail["final_url"] = str(resp.url) if getattr(resp, "url", None) else current
        detail["redirect_chain"] = chain

        if resp.status_code >= 400:
            detail["fetch_error"] = f"http_{resp.status_code}"
            return detail

        html = resp.text or ""
        soup = BeautifulSoup(html, "html.parser")
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        visible = soup.get_text(" ", strip=True)
        page_text = _normalize_page_text(html, visible)

        detail["page_title"] = title
        detail["html"] = html
        detail["html_length"] = len(html)
        detail["visible_text_length"] = len(visible)
        detail["html_loaded"] = len(html) >= 100
        detail["page_text"] = page_text

        if len(page_text) < 80:
            detail["fetch_error"] = "empty_body"
            detail["ok"] = False
        else:
            detail["ok"] = True
            detail["fetch_error"] = None
        return detail

    except (InvalidSchema, MissingSchema):
        detail["fetch_error"] = "invalid_redirect_scheme"
        return detail
    except requests.Timeout:
        detail["fetch_error"] = "timeout"
        return detail
    except requests.RequestException:
        detail["fetch_error"] = "request_error"
        return detail
    except Exception:
        detail["fetch_error"] = "unexpected"
        return detail


def _fetch_playwright(url: str) -> dict[str, Any]:
    detail = _base_detail(url)
    detail["attempted_playwright"] = True
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        detail["fetch_error"] = "playwright_missing"
        return detail

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=_headless(), args=_CHROMIUM_ARGS)
            try:
                page = browser.new_page(
                    user_agent=_SESSION.headers.get("User-Agent"),
                    locale="en-PH",
                )
                page.goto(url, wait_until="domcontentloaded", timeout=int(FETCH_TIMEOUT_SEC * 1000))
                page.wait_for_timeout(_PLAYWRIGHT_WAIT_MS)
                try:
                    page.evaluate("window.scrollTo(0, 500)")
                    page.wait_for_timeout(800)
                except Exception:
                    pass

                final_url = page.url
                title = page.title() or ""
                html = page.content()
                visible = page.inner_text("body")
                dom_snippets: list[str] = []
                try:
                    raw = page.evaluate(_DOM_JS)
                    if isinstance(raw, list):
                        dom_snippets = [str(x).strip() for x in raw if str(x).strip()]
                except Exception:
                    pass

            finally:
                browser.close()

        page_text = _normalize_page_text(html, visible)
        detail["final_url"] = final_url
        if detail["redirect_chain"]:
            if final_url not in detail["redirect_chain"]:
                detail["redirect_chain"] = detail["redirect_chain"] + [final_url]
        else:
            detail["redirect_chain"] = [url, final_url]

        detail["page_title"] = title
        detail["html"] = html
        detail["html_length"] = len(html)
        detail["visible_text_length"] = len(visible)
        detail["html_loaded"] = len(html) >= 100
        detail["page_text"] = page_text
        detail["dom_snippets"] = dom_snippets
        detail["http_status"] = 200

        if len(page_text) < 80:
            detail["fetch_error"] = "empty_body_pw"
            detail["ok"] = False
        else:
            detail["ok"] = True
            detail["fetch_error"] = None
        return detail

    except Exception as exc:
        logger.warning("TikTok Playwright error for %s: %s", url[:80], type(exc).__name__)
        detail["fetch_error"] = "playwright_error"
        return detail
