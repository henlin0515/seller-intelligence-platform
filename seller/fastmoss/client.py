"""Shared FastMoss HTTP client — JSON API only (no homepage HTML scrape)."""

from __future__ import annotations

import logging
import os
import random
import re
import threading
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("seller.fastmoss.client")

DEFAULT_BASE_URL = "https://www.fastmoss.com"
DEFAULT_REGION = "PH"
def _env_timeout_sec() -> float:
    ms = (os.getenv("FASTMOSS_REQUEST_TIMEOUT_MS") or "").strip()
    if ms:
        return max(1.0, float(ms) / 1000.0)
    return float(os.getenv("FASTMOSS_REQUEST_TIMEOUT_SEC", "30"))


# Prefer FASTMOSS_API_BASE_URL; fall back to FASTMOSS_BASE_URL for compatibility.
REQUEST_TIMEOUT_SEC = _env_timeout_sec()
REQUEST_DELAY_SEC = float(os.getenv("FASTMOSS_REQUEST_DELAY_SEC", "1.25"))
REQUEST_DELAY_MIN_SEC = float(os.getenv("FASTMOSS_REQUEST_DELAY_MIN_SEC", "1.0"))
REQUEST_DELAY_MAX_SEC = float(os.getenv("FASTMOSS_REQUEST_DELAY_MAX_SEC", "3.0"))
MAX_RETRIES = int(
    os.getenv("FASTMOSS_RETRY_COUNT")
    or os.getenv("FASTMOSS_MAX_RETRIES", "3")
)
MAX_CONCURRENCY = int(os.getenv("FASTMOSS_MAX_CONCURRENCY", "3"))
RETRY_BACKOFF_SEC = float(os.getenv("FASTMOSS_RETRY_BACKOFF_SEC", "1.5"))
RECENT_DATA_PATH = "/api/shop/v3/recentData"

_SECRET_RE = re.compile(
    r"(?i)\b((?:authorization|cookie|x-api-key|api[_-]?key|access[_-]?token)\s*[:=]\s*)"
    r"(?:Bearer\s+)?\S+"
)

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
    return (
        os.getenv("FASTMOSS_API_BASE_URL")
        or os.getenv("FASTMOSS_BASE_URL")
        or DEFAULT_BASE_URL
    ).rstrip("/")


def region() -> str:
    return (os.getenv("FASTMOSS_REGION") or DEFAULT_REGION).strip().upper() or DEFAULT_REGION


def _access_token() -> str:
    return (os.getenv("FASTMOSS_ACCESS_TOKEN") or "").strip()


def _api_key() -> str:
    return (os.getenv("FASTMOSS_API_KEY") or "").strip()


def credentials_configured() -> bool:
    """True when cookie, Bearer token, or API key is present."""
    return bool(_env_cookie() or _access_token() or _api_key())


def mask_secrets(text: str) -> str:
    """Redact credential-looking fragments from logs / diagnostics."""
    return _SECRET_RE.sub(r"\1[REDACTED]", text or "")


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
    token = _access_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    api_key = _api_key()
    if api_key:
        headers["X-API-Key"] = api_key
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


def apply_auth_headers(session: requests.Session) -> None:
    """Refresh Authorization / X-API-Key / Cookie from env onto the session."""
    session.headers.update(default_headers())
    apply_cookie_header(session)


def new_session() -> requests.Session:
    session = requests.Session()
    apply_auth_headers(session)
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


def _retry_after_seconds(resp: requests.Response, attempt: int) -> float:
    raw = (resp.headers.get("Retry-After") or "").strip()
    if raw:
        try:
            return max(0.5, float(raw))
        except ValueError:
            pass
    return RETRY_BACKOFF_SEC * attempt + random.uniform(0.2, 0.8)


class FastMossAuthError(RuntimeError):
    """Raised when FastMoss returns 401/403 — stop the batch immediately."""

    def __init__(self, status_code: int, message: str = ""):
        self.status_code = status_code
        self.error_code = "AUTH_REQUIRED"
        super().__init__(message or f"FastMoss AUTH_REQUIRED HTTP {status_code}")


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
    """
    HTTP request with throttle + retries on 429/5xx/timeout only.

    Never retries 400/401/403/404. 401/403 raise FastMossAuthError immediately.
    """
    attempts = MAX_RETRIES if retries is None else max(1, int(retries))
    soft = soft_fail_statuses or set()
    last_exc: BaseException | None = None
    resp: requests.Response | None = None
    safe_url = mask_secrets(url)

    for attempt in range(1, attempts + 1):
        if throttle_before:
            throttle()
        try:
            resp = session.request(method, url, timeout=REQUEST_TIMEOUT_SEC, **kwargs)
            code = int(resp.status_code)
            if code in {401, 403}:
                logger.error(
                    "FastMoss AUTH_REQUIRED HTTP %s for %s — stopping retries",
                    code,
                    safe_url,
                )
                raise FastMossAuthError(code, f"HTTP {code}")
            if code in RETRYABLE_STATUS and attempt < attempts:
                wait = _retry_after_seconds(resp, attempt)
                logger.warning(
                    "FastMoss retryable status %s for %s (attempt %s/%s) wait=%.1fs",
                    code,
                    safe_url,
                    attempt,
                    attempts,
                    wait,
                )
                time.sleep(wait)
                continue
            if code in soft:
                logger.warning(
                    "FastMoss soft-fail status %s for %s after %s attempt(s)",
                    code,
                    safe_url,
                    attempt,
                )
                return resp
            if raise_for_status:
                resp.raise_for_status()
            return resp
        except FastMossAuthError:
            raise
        except Exception as exc:
            last_exc = exc
            if attempt < attempts and _is_retryable_http_error(exc):
                logger.warning(
                    "FastMoss request error on %s (attempt %s/%s): %s",
                    safe_url,
                    attempt,
                    attempts,
                    mask_secrets(str(exc)),
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
    if code == 429:
        return "rate_limited"
    if code in RETRYABLE_STATUS or code in {567, 587}:
        return "blocked"
    if code == 404 or "not found" in text:
        return "path"
    if code == 0:
        return "network"
    return "unknown"


def _failure_ui_code(failure_class: str | None) -> str:
    mapping = {
        "auth": "FASTMOSS_AUTH_REQUIRED",
        "rate_limited": "FASTMOSS_RATE_LIMITED",
        "safe_lock": "FASTMOSS_AUTH_REQUIRED",
        "path": "FASTMOSS_API_NOT_CONFIGURED",
        "network": "FASTMOSS_PARTIAL_FAILURE",
        "failed": "FASTMOSS_PARTIAL_FAILURE",
        "blocked": "FASTMOSS_RATE_LIMITED",
        "unknown": "FASTMOSS_PARTIAL_FAILURE",
    }
    return mapping.get(str(failure_class or ""), "FASTMOSS_PARTIAL_FAILURE")


def healthcheck(*, shop_id: str | None = None) -> dict[str, Any]:
    """
    Probe FastMoss JSON API only (`GET /api/shop/v3/recentData`).

    Does not hit the HTML homepage or shop-detail pages (those trigger WAF 502).
    """
    global _last_health
    from seller.intelligence.business_time import business_today
    from seller.intelligence.periods import resolve_periods

    probe_shop = (
        shop_id or os.getenv("FASTMOSS_HEALTHCHECK_SHOP_ID") or "7494600626141628535"
    ).strip()
    cookie_on = cookie_configured()
    creds_on = credentials_configured()
    periods = resolve_periods(business_today())
    result: dict[str, Any] = {
        "ok": False,
        "cookie_configured": cookie_on,
        "credentials_configured": creds_on,
        "base_url": base_url(),
        "api_path": RECENT_DATA_PATH,
        "region": region(),
        "probe_shop_id": probe_shop,
        "home_status": None,  # deprecated — never probed
        "detail_status": None,  # deprecated — never probed
        "api_status": None,
        "api_code": None,
        "mode": None,
        "failure_class": None,
        "error_code": None,
        "message": None,
        "action": None,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    def _probe(session: requests.Session, mode: str) -> bool:
        result["mode"] = mode
        params = {
            "id": probe_shop,
            "start_date": periods.mtd.start.isoformat(),
            "end_date": periods.mtd.end.isoformat(),
            "region": region(),
            "_time": str(int(time.time())),
            "cnonce": str(random.randint(10_000_000, 99_999_999)),
        }
        api = request_with_retry(
            session,
            "GET",
            f"{base_url()}{RECENT_DATA_PATH}",
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
        if api.status_code in {401, 403}:
            result["failure_class"] = "auth"
            result["error_code"] = "FASTMOSS_AUTH_REQUIRED"
            result["message"] = f"FastMoss recentData HTTP {api.status_code}"
            return False
        if api.status_code == 429:
            result["failure_class"] = "rate_limited"
            result["error_code"] = "FASTMOSS_RATE_LIMITED"
            result["message"] = "FastMoss recentData HTTP 429"
            return False
        # HTTP 200 + JSON body proves the shop recentData endpoint is reachable.
        if api.status_code == 200 and isinstance(payload, dict):
            result["ok"] = True
            result["error_code"] = "SUCCESS"
            result["message"] = f"FastMoss recentData reachable via {mode} (api_code={code})"
            return True

        result["failure_class"] = classify_failure(api.status_code, (api.text or "")[:500])
        if str(code).startswith("MSG_SAFE"):
            result["failure_class"] = "safe_lock"
        result["error_code"] = _failure_ui_code(result["failure_class"])
        result["message"] = (
            f"FastMoss recentData failed via {mode} HTTP {api.status_code} "
            f"api_code={code}"
        )
        return False

    try:
        # Prefer anonymous: logged-in Cookie often returns MSG_SAFE_0001 after bulk use.
        if not _probe(anonymous_session(), "anonymous") and cookie_on:
            _probe(new_session(), "cookie")
    except FastMossAuthError as exc:
        result["failure_class"] = "auth"
        result["error_code"] = "FASTMOSS_AUTH_REQUIRED"
        result["message"] = str(exc)
    except Exception as exc:
        result["failure_class"] = "network"
        result["error_code"] = "FASTMOSS_PARTIAL_FAILURE"
        result["message"] = mask_secrets(str(exc))

    if not result["ok"]:
        fc = result.get("failure_class")
        result["error_code"] = result.get("error_code") or _failure_ui_code(fc)
        if fc == "safe_lock":
            result["action"] = (
                "FastMoss MSG_SAFE lock on logged-in Cookie. "
                "Collector prefers anonymous recentData retries."
            )
        elif fc == "auth":
            result["action"] = (
                "FastMoss API 驗證失敗，請更新合法的 API 憑證 "
                "(FASTMOSS_ACCESS_TOKEN / FASTMOSS_API_KEY / FASTMOSS_COOKIE)。"
            )
        elif fc == "rate_limited":
            result["action"] = (
                "FastMoss API 已達請求限制，系統會依 Retry-After 稍後重試。"
            )
        elif fc == "path":
            result["action"] = (
                "FastMoss API endpoint 可能變更 — 確認 GET /api/shop/v3/recentData。"
            )
        else:
            result["action"] = (
                "部分店鋪資料可能更新失敗；頁面會保留上一次成功資料。"
            )

    _last_health = result
    level = logger.info if result["ok"] else logger.error
    level(
        "FastMoss healthcheck ok=%s mode=%s cookie=%s api=%s class=%s code=%s msg=%s",
        result["ok"],
        result.get("mode"),
        cookie_on,
        result.get("api_status"),
        result.get("failure_class"),
        result.get("error_code"),
        result.get("message"),
    )
    if result.get("action") and not result["ok"]:
        logger.error("FastMoss action required: %s", result["action"])
    return result


def get_last_health() -> dict[str, Any] | None:
    return dict(_last_health) if _last_health else None
