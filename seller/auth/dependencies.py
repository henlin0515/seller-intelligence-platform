"""FastAPI dependencies for route-level auth (backup to middleware)."""

from __future__ import annotations

from fastapi import HTTPException, Request

from seller.auth.config import get_auth_settings
from seller.auth.session import is_session_authenticated


def require_auth(request: Request) -> str:
    settings = get_auth_settings()
    if not is_session_authenticated(request, inactivity_seconds=settings.inactivity_seconds):
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(request.session.get("username") or "")
