"""Authentication API — login, logout, session status."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from seller.auth.brute_force import check_lockout, clear_attempts, record_failed_attempt
from seller.auth.config import get_auth_settings
from seller.auth.session import (
    destroy_session,
    establish_session,
    is_session_authenticated,
    session_public_view,
)
from seller.auth.users import authenticate, list_auth_users

logger = logging.getLogger("auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "Invalid username or password"


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    settings = get_auth_settings()
    ip = _client_ip(request)

    lock = check_lockout(
        ip,
        max_attempts=settings.max_login_attempts,
        lockout_seconds=settings.lockout_seconds,
    )
    if lock.locked:
        logger.warning("Login blocked (lockout) ip=%s", ip)
        raise HTTPException(status_code=429, detail=GENERIC_LOGIN_ERROR)

    if not list_auth_users():
        logger.error("Login rejected: no auth users configured")
        raise HTTPException(status_code=503, detail=GENERIC_LOGIN_ERROR)

    user = authenticate(body.username, body.password)
    if user is None:
        record_failed_attempt(
            ip,
            username=body.username,
            max_attempts=settings.max_login_attempts,
            lockout_seconds=settings.lockout_seconds,
        )
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    clear_attempts(ip)
    establish_session(request.session, user.username, role=user.role)
    logger.info("Successful login ip=%s username=%s role=%s", ip, user.username, user.role)
    return {"ok": True, **session_public_view(request)}


@router.post("/logout")
async def logout(request: Request):
    destroy_session(request.session)
    return {"ok": True, "authenticated": False}


@router.get("/me")
async def me(request: Request):
    settings = get_auth_settings()
    if not is_session_authenticated(request, inactivity_seconds=settings.inactivity_seconds):
        return {"authenticated": False, "username": None}
    return session_public_view(request)
