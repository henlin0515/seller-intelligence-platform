"""
Shopee Seller AI Assistant — FastAPI web app.
Reuses search.py, claude_client.py, program_dictionary.py, query_mode.py.
"""

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from assistant_service import process_question
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

app = FastAPI(title="Shopee Seller AI Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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


@app.get("/")
async def index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(index_file)


@app.on_event("startup")
async def on_startup() -> None:
    clear_settings_cache()
    log_startup_configuration()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/seller/status")
async def seller_data_status():
    return get_seller_data_status()


@app.post("/api/seller/refresh")
async def seller_data_refresh():
    from seller.sheets_cache import refresh

    try:
        return await asyncio.to_thread(refresh, force=True)
    except Exception as exc:
        logger.exception("Seller sheet refresh failed")
        raise HTTPException(
            status_code=500,
            detail="Could not refresh mirror Google Sheet. Check credentials and sharing.",
        ) from exc


@app.get("/api/seller/search")
async def seller_search(q: str = ""):
    return {"results": search_seller_shops(q)}


@app.get("/api/seller/debug/{shop_id}")
async def seller_raw_debug(shop_id: str):
    """Temporary: live raw row only (no metric calculation)."""
    payload = get_raw_debug_payload(shop_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Shop not found")
    return payload


@app.get("/api/seller/{shop_id}")
async def seller_dashboard(shop_id: str):
    payload = get_dashboard_payload(shop_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Shop not found")
    return payload


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
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
