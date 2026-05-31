"""Global authentication gate and security response headers."""

from __future__ import annotations

import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from seller.auth.config import get_auth_settings
from seller.auth.session import is_session_authenticated

logger = logging.getLogger("auth.middleware")

# (method, path) exact matches — no auth required
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/login"),
        ("GET", "/health"),
        ("GET", "/robots.txt"),
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/logout"),
        ("GET", "/api/auth/me"),
    }
)

PUBLIC_PREFIXES: tuple[str, ...] = (
    "/static/",
)


def _is_public(request: Request) -> bool:
    path = request.url.path
    if any(path.startswith(p) for p in PUBLIC_PREFIXES):
        # Only login.html is public; block other HTML shells under /static/
        if path.endswith(".html") and path != "/static/login.html":
            return False
        return True
    return (request.method.upper(), path) in PUBLIC_ROUTES


def _wants_json(request: Request) -> bool:
    if request.url.path.startswith("/api/"):
        return True
    accept = request.headers.get("accept", "")
    return "application/json" in accept


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if _is_public(request):
            return await call_next(request)

        settings = get_auth_settings()
        if not is_session_authenticated(
            request, inactivity_seconds=settings.inactivity_seconds
        ):
            if _wants_json(request):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required"},
                )
            return RedirectResponse(url="/login", status_code=303)

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, hsts: bool = True) -> None:
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        csp = (
            "default-src 'self'; "
            "script-src 'self' https://esm.sh; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers["Content-Security-Policy"] = csp
        if self._hsts:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response
