"""Shared FastMoss HTTP client — cookies, throttle, retry, healthcheck."""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("seller.fastmoss.client")

DEFAULT_BASE_URL = "https://www.fastmoss.com"
DEFAULT_REGION = "PH"
REQUEST_TIMEOUT_SEC = float(os.getenv("FASTMOSS_REQUEST_TIMEOUT_SEC", "25"))
REQUEST_DELAY_SEC = float(os.getenv("FASTMOSS_REQUEST_DELAY_SEC", "1.25"))
REQUEST_DELAY_MIN_SEC = float(os.getenv("FASTMOSS_REQUEST_DELAY_MIN_SEC", "1.0"))
REQUEST_DELAY_MAX_SEC = float(os.getenv("FASTMOSS_REQUEST_DELAY_MAX_SEC", "3.0"))
MAX_RETRIES = int(os.getenv("FASTMOSS_MAX_RETRIES", "3"))
RETRY_BACKOFF_SEC = float(os.getenv("FASTMOSS_RETRY_BACKOFF_SEC", "1.5"))

# FastMoss / CDN WAF often returns non-standard 5xx (567/587) under bot pressure.
RETRYABLE_STATUS = {
    408,
    425,
    429,
    500,
    502,
    503,
    504,
    520,
    521,
    522,
    523,
    524,
    525,
    526,
    530,
    567,
    587,
}

_thr_lock = threading.Lock()
_last_request_monotonic = 0.0
_session_lock = threading.Lock()
_shared_session: requests.Session | None = None
_last_health: dict[str, Any] | None = None


def _resolve_cookie_file(path: str) -> Path:
    """Resolve cookie file path (relative paths are from repo root)."""
    candidate = Path(path)
    if candidate.is_file():
        return candidate
    root = Path(__file__).resolve().parents[2]
    rooted = root / path
    if rooted.is_file():
        return rooted
    return candidate


def _env_cookie() -> str:
    raw = (os.getenv("FASTMOSS_COOKIE") or "").strip()
    if raw:
        return raw
    path = (os.getenv("FASTMOSS_COOKIE_FILE") or "").strip()
    if path:
        resolved = _resolve_cookie_file(path)
        try:
            return resolved.read_text(encoding="utf-8").strip()
        except OSError as exc:
            logger.warning("Could not read FASTMOSS_COOKIE_FILE %s: %s", resolved, exc)
    return ""


def cookie_configured() -> bool:
    return bool(_env_cookie())


def base_url() -> str:
    return (os.getenv("FASTMOSS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def region() -> str:
    return (os.getenv("FASTMOSS_REGION") or DEFAULT_REGION).strip().upper() or DEFAULT_REGION


def default_headers(*, referer: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": (
            os.getenv("FASTMOSS_USER_AGENT")
            or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "lang": "EN_US",
        "region": region(),
        "source": "pc",
        "Origin": base_url(),
    }
    if referer:
        headers["Referer"] = referer
    return headers


def apply_cookie_header(session: requests.Session) -> bool:
    """Apply FASTMOSS_COOKIE / FASTMOSS_COOKIE_FILE onto the session."""
    cookie = _env_cookie()
    if not cookie:
        session.headers.pop("Cookie", None)
        return False
    session.headers["Cookie"] = cookie
    return True


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(default_headers())
    apply_cookie_header(session)
    return session


def anonymous_session() -> requests.Session:
    """Session without FastMoss login Cookie — avoids MSG_SAFE_0001 lockouts."""
    session = requests.Session()
    session.headers.update(default_headers())
    session.headers.pop("Cookie", None)
    return session


def get_shared_session(*, refresh: bool = False) -> requests.Session:
    global _shared_session
    with _session_lock:
        if _shared_session is None or refresh:
            _shared_session = new_session()
        else:
            apply_cookie_header(_shared_session)
        return _shared_session


def throttle(*, min_sec: float | None = None, max_sec: float | None = None) -> float:
    """Sleep a random interval so bulk scrapes do not burst FastMoss anti-bot."""
    global _last_request_monotonic
    lo = REQUEST_DELAY_MIN_SEC if min_sec is None else float(min_sec)
    hi = REQUEST_DELAY_MAX_SEC if max_sec is None else float(max_sec)
    if hi < lo:
        hi = lo
    gap = random.uniform(lo, hi) if hi > 0 else 0.0
    with _thr_lock:
        now = time.monotonic()
        wait = (_last_request_monotonic + gap) - now
        if wait > 0:
            time.sleep(wait)
        _last_request_monotonic = time.monotonic()
    return gap


def _is_retryable_http_error(exc: BaseException) -> bool:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return int(exc.response.status_code) in RETRYABLE_STATUS
    return False


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    retries: int | None = None,
    throttle_before: bool = True,
    raise_for_status: bool = True,
    soft_fail_statuses: set[int] | None = None,
    **kwargs: Any,
) -> requests.Response:
    """HTTP request with throttle + retries on 5xx/429/567/587."""
    attempts = MAX_RETRIES if retries is None else max(1, int(retries))
    soft = soft_fail_statuses or set()
    last_exc: BaseException | None = None
    resp: requests.Response | None = None

    for attempt in range(1, attempts + 1):
        if throttle_before:
            throttle()
        try:
            resp = session.request(method, url, timeout=REQUEST_TIMEOUT_SEC, **kwargs)
            code = int(resp.status_code)
            if code in RETRYABLE_STATUS and attempt < attempts:
                logger.warning(
                    "FastMoss retryable status %s for %s (attempt %s/%s)",
                    code,
                    url,
                    attempt,
                    attempts,
                )
                time.sleep(RETRY_BACKOFF_SEC * attempt + random.uniform(0.2, 0.8))
                continue
            # Soft-fail only after retries are exhausted (e.g. detail prefetch 567/587).
            if code in soft:
                logger.warning(
                    "FastMoss soft-fail status %s for %s after %s attempt(s)",
                    code,
                    url,
                    attempt,
                )
                return resp
            if raise_for_status:
                resp.raise_for_status()
            return resp
        except Exception as exc:
            last_exc = exc
            if attempt < attempts and _is_retryable_http_error(exc):
                logger.warning(
                    "FastMoss request error on %s (attempt %s/%s): %s",
                    url,
                    attempt,
                    attempts,
                    exc,
                )
                time.sleep(RETRY_BACKOFF_SEC * attempt + random.uniform(0.2, 0.8))
                continue
            raise

    if resp is not None:
        if raise_for_status:
            resp.raise_for_status()
        return resp
    assert last_exc is not None
    raise last_exc


def classify_failure(status_code: int | None, body_snippet: str = "") -> str:
    text = (body_snippet or "").lower()
    code = int(status_code or 0)
    if code in {401, 403} or "login" in text or "unauthorized" in text:
        return "auth"
    if code in RETRYABLE_STATUS or code in {567, 587}:
        return "blocked"
    if code == 404 or "not found" in text:
        return "path"
    if code == 0:
        return "network"
    return "unknown"


def healthcheck(*, shop_id: str | None = None) -> dict[str, Any]:
    """Ping FastMoss before bulk scrapes (homepage + detail + recentData)."""
    global _last_health
    probe_shop = (
        shop_id or os.getenv("FASTMOSS_HEALTHCHECK_SHOP_ID") or "7494600626141628535"
    ).strip()
    cookie_on = cookie_configured()
    result: dict[str, Any] = {
        "ok": False,
        "cookie_configured": cookie_on,
        "base_url": base_url(),
        "region": region(),
        "probe_shop_id": probe_shop,
        "home_status": None,
        "detail_status": None,
        "api_status": None,
        "api_code": None,
        "mode": None,
        "failure_class": None,
        "message": None,
        "action": None,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    def _probe(session: requests.Session, mode: str) -> bool:
        from datetime import date, timedelta

        home = request_with_retry(
            session,
            "GET",
            f"{base_url()}/",
            retries=2,
            raise_for_status=False,
        )
        result["home_status"] = home.status_code
        result["mode"] = mode
        if home.status_code >= 400:
            result["failure_class"] = classify_failure(home.status_code, home.text[:500])
            result["message"] = f"FastMoss homepage returned HTTP {home.status_code}"
            return False

        detail = request_with_retry(
            session,
            "GET",
            f"{base_url()}/shop-marketing/detail/{probe_shop}",
            retries=MAX_RETRIES,
            raise_for_status=False,
            soft_fail_statuses=RETRYABLE_STATUS,
        )
        result["detail_status"] = detail.status_code

        end = date.today() - timedelta(days=1)
        start = end.replace(day=1)
        params = {
            "id": probe_shop,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "region": region(),
            "_time": str(int(time.time())),
            "cnonce": str(random.randint(10_000_000, 99_999_999)),
        }
        api = request_with_retry(
            session,
            "GET",
            f"{base_url()}/api/shop/v3/recentData",
            params=params,
            headers={"Referer": f"{base_url()}/shop-marketing/detail/{probe_shop}"},
            retries=MAX_RETRIES,
            raise_for_status=False,
        )
        result["api_status"] = api.status_code
        try:
            payload = api.json()
        except Exception:
            payload = {}
        result["api_code"] = payload.get("code")
        code = payload.get("code")
        if api.status_code == 200 and code in (200, "200"):
            result["ok"] = True
            result["message"] = f"FastMoss reachable via {mode}; recentData OK"
            if detail.status_code in RETRYABLE_STATUS:
                result["message"] += (
                    f" (detail page HTTP {detail.status_code} — will soft-skip prefetch)"
                )
            return True

        result["failure_class"] = classify_failure(api.status_code, (api.text or "")[:500])
        if str(code).startswith("MSG_SAFE"):
            result["failure_class"] = "safe_lock"
        result["message"] = (
            f"FastMoss recentData failed via {mode} HTTP {api.status_code} "
            f"api_code={code} msg={payload.get('msg') or payload.get('message')}"
        )
        return False

    try:
        # Prefer anonymous: logged-in Cookie often returns MSG_SAFE_0001 after bulk use.
        if not _probe(anonymous_session(), "anonymous") and cookie_on:
            _probe(new_session(), "cookie")
    except Exception as exc:
        result["failure_class"] = "network"
        result["message"] = str(exc)

    if not result["ok"]:
        fc = result.get("failure_class")
        if fc == "safe_lock":
            result["action"] = (
                "FastMoss MSG_SAFE lock on logged-in Cookie. "
                "Collector will prefer anonymous recentData retries."
            )
        elif fc == "auth" or (not cookie_on and fc in {"blocked", "unknown"}):
            result["action"] = (
                "Set FASTMOSS_COOKIE (or FASTMOSS_COOKIE_FILE) from a logged-in "
                "browser session on www.fastmoss.com, then restart the service."
            )
        elif fc == "blocked":
            result["action"] = (
                "FastMoss WAF/anti-bot blocked this IP (567/587). "
                "Slow down requests and retry later."
            )
        elif fc == "path":
            result["action"] = (
                "FastMoss API path may have changed — check /api/shop/v3/recentData."
            )
        else:
            result["action"] = "Check network / FastMoss status and retry."

    _last_health = result
    level = logger.info if result["ok"] else logger.error
    level(
        "FastMoss healthcheck ok=%s mode=%s cookie=%s home=%s detail=%s api=%s class=%s msg=%s",
        result["ok"],
        result.get("mode"),
        cookie_on,
        result.get("home_status"),
        result.get("detail_status"),
        result.get("api_status"),
        result.get("failure_class"),
        result.get("message"),
    )
    if result.get("action") and not result["ok"]:
        logger.error("FastMoss action required: %s", result["action"])
    return result


def get_last_health() -> dict[str, Any] | None:
    return dict(_last_health) if _last_health else None
