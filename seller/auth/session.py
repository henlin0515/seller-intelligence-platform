"""Server-side session helpers (Starlette SessionMiddleware)."""

from __future__ import annotations

import time
from typing import Any

from starlette.requests import Request

SESSION_AUTH_KEY = "authenticated"
SESSION_USER_KEY = "username"
SESSION_ROLE_KEY = "role"
SESSION_ACTIVITY_KEY = "last_activity"


def is_session_authenticated(request: Request, *, inactivity_seconds: int) -> bool:
    session = request.session
    if not session.get(SESSION_AUTH_KEY):
        return False
    last = session.get(SESSION_ACTIVITY_KEY)
    if last is None:
        return False
    try:
        last_f = float(last)
    except (TypeError, ValueError):
        return False
    if time.time() - last_f > inactivity_seconds:
        destroy_session(session)
        return False
    session[SESSION_ACTIVITY_KEY] = time.time()
    return True


def establish_session(session: dict[str, Any], username: str, *, role: str | None = None) -> None:
    session.clear()
    session[SESSION_AUTH_KEY] = True
    session[SESSION_USER_KEY] = username
    if role:
        session[SESSION_ROLE_KEY] = role
    session[SESSION_ACTIVITY_KEY] = time.time()


def destroy_session(session: dict[str, Any]) -> None:
    session.clear()


def session_public_view(request: Request) -> dict[str, Any]:
    session = request.session
    authenticated = bool(session.get(SESSION_AUTH_KEY))
    return {
        "authenticated": authenticated,
        "username": session.get(SESSION_USER_KEY) if authenticated else None,
        "role": session.get(SESSION_ROLE_KEY) if authenticated else None,
    }
