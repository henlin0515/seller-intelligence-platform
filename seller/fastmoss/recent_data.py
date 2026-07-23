"""FastMoss shop recentData — period GMV from total_info.sale_amount."""

from __future__ import annotations

import logging
import os
import random
import time
from datetime import date
from typing import Any

import requests

from seller.fastmoss.client import (
    REQUEST_DELAY_SEC,
    REQUEST_TIMEOUT_SEC,
    RETRYABLE_STATUS,
    anonymous_session,
    base_url,
    get_shared_session,
    new_session,
    region,
    request_with_retry,
)

logger = logging.getLogger("seller.fastmoss.recent_data")

RECENT_DATA_PATH = "/api/shop/v3/recentData"

# Paywall placeholder FastMoss returns under MAG_AUTH when not authorized.
_PAYWALL_SENTINEL_SALE = 142217262690.98
_SAFE_CODES = {"MSG_SAFE_0001", "MSG_SAFE_0002"}
_MAX_LOGIC_RETRIES = int(os.getenv("FASTMOSS_LOGIC_RETRIES", "8"))

# Backward-compatible aliases used by goods / radar / older scripts.
_base_url = base_url
_region = region


def _detail_referer(shop_id: str) -> str:
    return f"{base_url()}/shop-marketing/detail/{shop_id}"


def prefetch_shop_detail(
    fastmoss_shop_id: str,
    session: requests.Session | None = None,
) -> requests.Session:
    """
    Visit shop detail page to satisfy FastMoss view quota.

    Soft-fails on WAF 5xx (567/587): returns the session so recentData can still run.
    """
    shop_id = str(fastmoss_shop_id or "").strip()
    if not shop_id:
        raise ValueError("fastmoss_shop_id is required")
    client = session or anonymous_session()
    url = _detail_referer(shop_id)
    resp = request_with_retry(
        client,
        "GET",
        url,
        raise_for_status=False,
        soft_fail_statuses=RETRYABLE_STATUS,
    )
    if resp.status_code >= 400:
        logger.warning(
            "FastMoss detail prefetch HTTP %s for %s — continuing without hard fail",
            resp.status_code,
            shop_id,
        )
        return client
    return client


def parse_period_metrics(total_info: dict[str, Any]) -> dict[str, int | float]:
    """Map FastMoss recentData total_info to SLA shop-detail metrics."""
    return {
        "sales_volume": int(total_info.get("sold_count") or 0),
        "sales_amount": round(float(total_info.get("sale_amount") or 0), 2),
        "creator_count": int(total_info.get("author_count") or 0),
        "live_count": int(total_info.get("live_count") or 0),
        "video_count": int(total_info.get("aweme_count") or 0),
        "active_product_count": int(total_info.get("sold_product_count") or 0),
    }


def _total_info_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return {}
    lst = data.get("list") or {}
    if not isinstance(lst, dict):
        return {}
    info = lst.get("total_info") or {}
    return info if isinstance(info, dict) else {}


def _is_paywall_placeholder(total_info: dict[str, Any]) -> bool:
    try:
        sale = float(total_info.get("sale_amount"))
    except (TypeError, ValueError):
        return False
    if abs(sale - _PAYWALL_SENTINEL_SALE) < 0.01:
        return True
    # Paywall stubs usually omit shop_name.
    if not str(total_info.get("shop_name") or "").strip() and sale > 1e11:
        return True
    return False


def _payload_has_usable_metrics(payload: dict[str, Any]) -> bool:
    code = payload.get("code")
    info = _total_info_from_payload(payload)
    if not info or info.get("sale_amount") is None:
        return False
    if _is_paywall_placeholder(info):
        return False
    if code in (200, "200"):
        return True
    # Some MAG_AUTH_* responses still include real metrics (with shop_name).
    if str(code).startswith("MAG_AUTH") and str(info.get("shop_name") or "").strip():
        return True
    return False


def _should_retry_logic(payload: dict[str, Any]) -> bool:
    code = str(payload.get("code") or "")
    if code in _SAFE_CODES:
        return True
    if code.startswith("MAG_AUTH"):
        info = _total_info_from_payload(payload)
        return (not info) or _is_paywall_placeholder(info) or not str(
            info.get("shop_name") or ""
        ).strip()
    return False


def fetch_recent_data(
    fastmoss_shop_id: str,
    start: date,
    end: date,
    *,
    session: requests.Session | None = None,
    prefetch_detail: bool = True,
    prefer_anonymous: bool = True,
) -> tuple[dict[str, Any], str, requests.Session]:
    """
    Fetch recentData for a FastMoss shop and date range.

    Strategy:
    - Prefer anonymous session (logged-in Cookie often trips MSG_SAFE_0001).
    - Retry on MSG_SAFE / paywall MAG_AUTH placeholders with backoff.
    - Fall back to cookie session once if anonymous keeps failing.
    """
    shop_id = str(fastmoss_shop_id or "").strip()
    if not shop_id:
        raise ValueError("fastmoss_shop_id is required")
    if end < start:
        raise ValueError("end_date must be on or after start_date")

    modes: list[tuple[str, requests.Session]] = []
    if prefer_anonymous:
        modes.append(("anonymous", session if session is not None else anonymous_session()))
        modes.append(("cookie", new_session()))
    else:
        modes.append(("cookie", session or get_shared_session()))
        modes.append(("anonymous", anonymous_session()))

    last_message = "unknown"
    last_client = modes[0][1]
    last_url = f"{base_url()}{RECENT_DATA_PATH}"

    for mode_name, base_client in modes:
        client = base_client
        for attempt in range(1, _MAX_LOGIC_RETRIES + 1):
            if prefetch_detail and attempt == 1:
                client = prefetch_shop_detail(shop_id, client)
            elif attempt > 1:
                # Rotate session after soft blocks.
                client = anonymous_session() if mode_name == "anonymous" else new_session()

            params = {
                "id": shop_id,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "region": region(),
                "_time": str(int(time.time())),
                "cnonce": str(random.randint(10_000_000, 99_999_999)),
            }
            url = f"{base_url()}{RECENT_DATA_PATH}"
            headers = {"Referer": _detail_referer(shop_id)}
            resp = request_with_retry(
                client,
                "GET",
                url,
                params=params,
                headers=headers,
                raise_for_status=False,
            )
            last_url = resp.url
            last_client = client
            try:
                payload: dict[str, Any] = resp.json()
            except Exception:
                last_message = f"HTTP {resp.status_code} non-JSON"
                time.sleep(1.2 * attempt + random.uniform(0.3, 1.0))
                continue

            if _payload_has_usable_metrics(payload):
                data = payload.get("data") or {}
                lst = data.get("list") or {}
                return {
                    "total_info": lst.get("total_info") or {},
                    "trend": lst.get("trend") or [],
                }, resp.url, client

            code = payload.get("code")
            last_message = str(
                payload.get("message") or payload.get("msg") or code or f"HTTP {resp.status_code}"
            )
            if _should_retry_logic(payload) and attempt < _MAX_LOGIC_RETRIES:
                logger.warning(
                    "FastMoss recentData %s for %s (%s attempt %s/%s) — retrying",
                    code,
                    shop_id,
                    mode_name,
                    attempt,
                    _MAX_LOGIC_RETRIES,
                )
                time.sleep(1.5 * attempt + random.uniform(0.5, 2.0))
                continue
            # Non-retryable for this mode — try next mode.
            break

    raise RuntimeError(f"FastMoss recentData error: {last_message}")


def fetch_shop_period_metrics(
    fastmoss_shop_id: str,
    start: date,
    end: date,
    *,
    session: requests.Session | None = None,
    prefetch_detail: bool = True,
) -> tuple[dict[str, int | float], str, requests.Session]:
    """Fetch period shop trend metrics from recentData total_info."""
    recent, request_url, client = fetch_recent_data(
        fastmoss_shop_id,
        start,
        end,
        session=session,
        prefetch_detail=prefetch_detail,
    )
    return parse_period_metrics(recent.get("total_info") or {}), request_url, client


def fetch_period_gmv_php(
    fastmoss_shop_id: str,
    start: date,
    end: date,
    *,
    session: requests.Session | None = None,
    prefetch_detail: bool = True,
) -> tuple[float, str, requests.Session]:
    """
    Fetch period GMV (PHP) from recentData total_info.sale_amount.

    Returns (sale_amount_php, request_url, session).
    """
    metrics, request_url, client = fetch_shop_period_metrics(
        fastmoss_shop_id,
        start,
        end,
        session=session,
        prefetch_detail=prefetch_detail,
    )
    sale_amount = metrics.get("sales_amount")
    if sale_amount is None:
        raise RuntimeError("FastMoss recentData missing total_info.sale_amount")
    return float(sale_amount), request_url, client
