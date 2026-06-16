"""
Shopee Seller AI Assistant — FastAPI web app.
Reuses search.py, claude_client.py, program_dictionary.py, query_mode.py.
"""

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from assistant_service import process_question
from seller.assortment.db import init_assortment_db
from seller.assortment.router import router as assortment_router
from seller.intelligence.router import router as intelligence_v1_router
from seller.auth.config import dev_session_secret, get_auth_settings, validate_auth_config
from seller.auth.dependencies import require_auth
from seller.auth.middleware import AuthMiddleware, SecurityHeadersMiddleware
from seller.auth.router import router as auth_router
from seller.competitor_tracker.service import (
    check_tiktok_vouchers_for_all,
    clear_competitor_sheet_cache,
    get_competitor_list_payload,
)
from seller.raw_debug import get_raw_debug_payload
from seller.service import (
    get_dashboard_payload,
    get_seller_data_status,
    search_seller_shops,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("shopee_assistant")

from seller.google_sheets.config import clear_settings_cache, log_startup_configuration
from search import chromium_executable_available

clear_settings_cache()
log_startup_configuration()
logger.info(
    "Playwright Chromium available: %s (HEADLESS=%s)",
    chromium_executable_available(),
    os.getenv("HEADLESS", "(unset)"),
)

USER_FACING_ERROR = (
    "Something went wrong while researching. "
    "Please try again or check the backend logs."
)

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"


def _session_secret() -> str:
    settings = get_auth_settings()
    if settings.session_secret:
        return settings.session_secret
    dev = dev_session_secret()
    if dev:
        logger.warning(
            "Using ephemeral AUTH session secret (AUTH_ALLOW_DEV_DEFAULTS). "
            "Set AUTH_SESSION_SECRET in production."
        )
        return dev
    validate_auth_config()
    return ""  # unreachable


_auth_settings = get_auth_settings()
app = FastAPI(title="Shopee Seller AI Assistant", version="1.0.0", docs_url=None, redoc_url=None)

# Middleware order: last added runs first on incoming requests.
# Session must run before Auth so request.session is available.
app.add_middleware(SecurityHeadersMiddleware, hsts=_auth_settings.cookie_secure)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret(),
    session_cookie=_auth_settings.session_cookie_name,
    max_age=_auth_settings.inactivity_seconds,
    same_site="strict",
    https_only=_auth_settings.cookie_secure,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

if STATIC_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth_router)
app.include_router(assortment_router, dependencies=[Depends(require_auth)])
app.include_router(intelligence_v1_router)


@app.get("/api/seller-level-analysis/shop-detail", dependencies=[Depends(require_auth)])
async def seller_level_analysis_shop_detail(
    shopee_shop_id: str,
    fastmoss_shop_id: str | None = None,
    tiktok_shop_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    platform_source: str = "",
):
    """Alias for SLA expandable row shop-detail (same handler as intelligence v1)."""
    from seller.intelligence.router import _shop_detail_handler

    return await _shop_detail_handler(
        shopee_shop_id=shopee_shop_id,
        fastmoss_shop_id=fastmoss_shop_id,
        tiktok_shop_id=tiktok_shop_id,
        start_date=start_date,
        end_date=end_date,
        platform_source=platform_source,
    )


class CompetitorCheckRequest(BaseModel):
    shop_ids: list[str] | None = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class SourceItem(BaseModel):
    title: str
    url: str
    type: str = "article"


class ChatResponse(BaseModel):
    answer: str
    key_points: list[str]
    sources: list[SourceItem]
    formatted: str
    mode: str


@app.get("/login")
async def login_page():
    login_file = STATIC_DIR / "login.html"
    if not login_file.is_file():
        raise HTTPException(status_code=404, detail="Login page not found")
    return FileResponse(login_file)


@app.get("/")
async def index(_user: str = Depends(require_auth)):
    index_file = STATIC_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(index_file)


@app.get("/robots.txt")
async def robots_txt():
    robots_file = STATIC_DIR / "robots.txt"
    if robots_file.is_file():
        return FileResponse(robots_file, media_type="text/plain")
    return PlainTextResponse("User-agent: *\nDisallow: /\n", media_type="text/plain")


@app.on_event("startup")
async def on_startup() -> None:
    validate_auth_config()
    clear_settings_cache()
    log_startup_configuration()
    init_assortment_db()
    try:
        from seller.fastmoss.review import ensure_review_store_synced, sync_manual_overrides_from_mapping_file

        ensure_review_store_synced()
        sync_manual_overrides_from_mapping_file()
    except Exception as exc:
        logger.warning("FastMoss mapping review bootstrap skipped: %s", exc)
    try:
        from seller.intelligence.bootstrap import maybe_start_background_sync

        maybe_start_background_sync()
    except Exception as exc:
        logger.warning("Intelligence background sync bootstrap skipped: %s", exc)
    logger.info("Authentication enabled for all protected routes")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/seller/status")
async def seller_data_status(_user: str = Depends(require_auth)):
    return get_seller_data_status()


@app.post("/api/seller/refresh")
async def seller_data_refresh(_user: str = Depends(require_auth)):
    from seller.sheets_cache import get_public_status, refresh

    try:
        await asyncio.to_thread(refresh, force=True)
        return get_public_status()
    except Exception as exc:
        logger.exception("Seller sheet refresh failed")
        raise HTTPException(
            status_code=500,
            detail="Could not refresh seller data. Try again later.",
        ) from exc


@app.get("/api/seller/search")
async def seller_search(q: str = "", _user: str = Depends(require_auth)):
    return {"results": search_seller_shops(q)}


def _debug_endpoint_enabled() -> bool:
    return os.getenv("ENABLE_SELLER_DEBUG_ENDPOINT", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


@app.get("/api/seller/debug/{shop_id}")
async def seller_raw_debug(shop_id: str, _user: str = Depends(require_auth)):
    """Disabled in production unless ENABLE_SELLER_DEBUG_ENDPOINT is set."""
    if not _debug_endpoint_enabled():
        raise HTTPException(status_code=404, detail="Not found")
    payload = get_raw_debug_payload(shop_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Shop not found")
    return payload


@app.get("/api/competitor-voucher/competitors")
async def competitor_voucher_list(refresh: bool = False, _user: str = Depends(require_auth)):
    """List competitors from COMPETITOR_TRACKER with cached voucher status."""
    if refresh:
        await asyncio.to_thread(clear_competitor_sheet_cache)
    return await asyncio.to_thread(get_competitor_list_payload, refresh_sheet=refresh)


@app.post("/api/competitor-voucher/check")
async def competitor_voucher_check(
    body: CompetitorCheckRequest, _user: str = Depends(require_auth)
):
    """Check selected shops (shop_ids) or all competitors (max 50 per run)."""
    try:
        return await asyncio.to_thread(
            check_tiktok_vouchers_for_all,
            shop_ids=body.shop_ids,
        )
    except Exception as exc:
        logger.exception("Competitor voucher check failed")
        raise HTTPException(
            status_code=500,
            detail="Could not complete voucher check. Try again later.",
        ) from exc


@app.get("/api/seller/{shop_id}")
async def seller_dashboard(shop_id: str, _user: str = Depends(require_auth)):
    payload = get_dashboard_payload(shop_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Shop not found")
    return payload


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, _user: str = Depends(require_auth)):
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY is not set")
        raise HTTPException(status_code=500, detail=USER_FACING_ERROR)

    try:
        result = await process_question(body.question)
        return ChatResponse(
            answer=result["answer"],
            key_points=result["key_points"],
            sources=[SourceItem(**s) for s in result["sources"]],
            formatted=result["formatted"],
            mode=result["mode"],
        )
    except ValueError as exc:
        logger.warning("Invalid chat request: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Please enter a valid question about Shopee programs or policies.",
        ) from exc
    except Exception as exc:
        logger.exception("Chat request failed")
        raise HTTPException(status_code=500, detail=USER_FACING_ERROR) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
