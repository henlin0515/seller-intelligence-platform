"""Unit tests for FastMoss shared HTTP client (throttle, retry, cookie, classify)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from seller.fastmoss.client import (
    RETRYABLE_STATUS,
    apply_cookie_header,
    classify_failure,
    cookie_configured,
    new_session,
    request_with_retry,
)


def test_classify_567_as_blocked():
    assert classify_failure(567) == "blocked"
    assert classify_failure(587) == "blocked"
    assert classify_failure(401) == "auth"
    assert classify_failure(404) == "path"


def test_cookie_from_env(monkeypatch):
    monkeypatch.delenv("FASTMOSS_COOKIE", raising=False)
    monkeypatch.delenv("FASTMOSS_COOKIE_FILE", raising=False)
    assert cookie_configured() is False

    monkeypatch.setenv("FASTMOSS_COOKIE", "sid=abc; token=xyz")
    assert cookie_configured() is True
    session = new_session()
    assert session.headers.get("Cookie") == "sid=abc; token=xyz"
    assert apply_cookie_header(session) is True


def test_request_retries_then_soft_fails_on_567():
    session = MagicMock()
    soft_resp = MagicMock()
    soft_resp.status_code = 567
    soft_resp.text = "blocked"
    session.request.return_value = soft_resp

    with patch("seller.fastmoss.client.throttle", return_value=0.0), patch(
        "seller.fastmoss.client.time.sleep"
    ):
        resp = request_with_retry(
            session,
            "GET",
            "https://www.fastmoss.com/shop-marketing/detail/1",
            retries=3,
            raise_for_status=False,
            soft_fail_statuses=RETRYABLE_STATUS,
        )

    assert resp.status_code == 567
    assert session.request.call_count == 3


def test_request_raises_after_retries_without_soft_fail():
    session = MagicMock()
    bad = MagicMock()
    bad.status_code = 567
    bad.raise_for_status.side_effect = requests.HTTPError("567", response=bad)
    session.request.return_value = bad

    with patch("seller.fastmoss.client.throttle", return_value=0.0), patch(
        "seller.fastmoss.client.time.sleep"
    ):
        with pytest.raises(requests.HTTPError):
            request_with_retry(
                session,
                "GET",
                "https://www.fastmoss.com/api/shop/v3/recentData",
                retries=2,
                raise_for_status=True,
            )

    assert session.request.call_count == 2
