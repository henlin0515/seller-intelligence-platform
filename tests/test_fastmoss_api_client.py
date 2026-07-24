"""Extra FastMoss client tests — auth stop, Retry-After, healthcheck JSON-only."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from seller.fastmoss.client import (
    FastMossAuthError,
    classify_failure,
    healthcheck,
    mask_secrets,
    request_with_retry,
)


def test_mask_secrets_redacts_cookie_and_bearer():
    text = "Cookie: secret=abc Authorization: Bearer tok123 X-API-Key: k9"
    out = mask_secrets(text)
    assert "tok123" not in out
    assert "secret=abc" not in out
    assert "[REDACTED]" in out


def test_401_raises_auth_error_without_retry():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 401
    resp.headers = {}
    session.request.return_value = resp

    with patch("seller.fastmoss.client.throttle", return_value=0.0), patch(
        "seller.fastmoss.client.time.sleep"
    ):
        with pytest.raises(FastMossAuthError):
            request_with_retry(
                session,
                "GET",
                "https://www.fastmoss.com/api/shop/v3/recentData",
                retries=5,
                raise_for_status=False,
            )
    assert session.request.call_count == 1


def test_429_honors_retry_after_then_succeeds():
    session = MagicMock()
    limited = MagicMock()
    limited.status_code = 429
    limited.headers = {"Retry-After": "0"}
    limited.raise_for_status.side_effect = requests.HTTPError("429", response=limited)
    ok = MagicMock()
    ok.status_code = 200
    ok.headers = {}
    session.request.side_effect = [limited, ok]

    with patch("seller.fastmoss.client.throttle", return_value=0.0), patch(
        "seller.fastmoss.client.time.sleep"
    ) as sleep:
        resp = request_with_retry(
            session,
            "GET",
            "https://www.fastmoss.com/api/shop/v3/recentData",
            retries=3,
            raise_for_status=False,
        )
    assert resp.status_code == 200
    assert session.request.call_count == 2
    assert sleep.called


def test_healthcheck_does_not_hit_homepage():
    api = MagicMock()
    api.status_code = 200
    api.text = '{"code":200}'
    api.json.return_value = {"code": 200, "data": {"list": {"total_info": {"sale_amount": 1}}}}

    session = MagicMock()
    urls: list[str] = []

    def _capture(method, url, **kwargs):
        urls.append(url)
        return api

    session.request.side_effect = _capture

    with (
        patch("seller.fastmoss.client.anonymous_session", return_value=session),
        patch("seller.fastmoss.client.throttle", return_value=0.0),
        patch("seller.fastmoss.client.cookie_configured", return_value=False),
        patch("seller.intelligence.business_time.business_today") as bt,
        patch("seller.intelligence.periods.resolve_periods") as rp,
    ):
        from datetime import date

        from seller.intelligence.periods import resolve_periods as real_resolve

        bt.return_value = date(2026, 7, 24)
        rp.return_value = real_resolve(date(2026, 7, 24))
        result = healthcheck(shop_id="7494600626141628535")

    assert result["ok"] is True
    assert result["error_code"] == "SUCCESS"
    assert all("/api/shop/v3/recentData" in u for u in urls)
    assert not any(u.rstrip("/").endswith("www.fastmoss.com") for u in urls)


def test_classify_429_rate_limited():
    assert classify_failure(429) == "rate_limited"
    assert classify_failure(567) == "blocked"
