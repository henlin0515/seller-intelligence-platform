"""TikTok Product Radar — permanent data source paths (do not change casually)."""

from __future__ import annotations

import os

# Shop list: Google Sheet tab (columns A–D via seller_master parser).
# Env override: GOOGLE_SHEET_SELLER_MASTER_TAB (default in seller_master.py: "shpoee link")
# Spreadsheet: GOOGLE_SHEET_MIRROR_ID (see .env.example)

# FastMoss shop mapping: fastmoss_mapping.json (refreshed from seller master on Update Data).

# Product catalog: FastMoss /api/shop/v3/goods for APPROVED mapped shops only.
FASTMOSS_GOODS_PATH = "/api/shop/v3/goods"
FASTMOSS_GOODS_MAX_PAGE_SIZE = 10

NEW_PRODUCT_DAYS = int(os.getenv("ASSORTMENT_NEW_PRODUCT_DAYS", "30"))
RADAR_MAX_PRODUCTS = int(
    os.getenv("ASSORTMENT_RADAR_MAX_PRODUCTS", os.getenv("FASTMOSS_MAX_PRODUCTS", "1000"))
)
RADAR_TOP_PER_SHOP = int(os.getenv("ASSORTMENT_RADAR_TOP_PER_SHOP", "30"))
RADAR_TOP_NEW_PER_SHOP = int(os.getenv("ASSORTMENT_RADAR_TOP_NEW_PER_SHOP", "10"))
RADAR_TOP_GROWTH = int(os.getenv("ASSORTMENT_RADAR_TOP_GROWTH", "30"))
RADAR_TOP_NEW = int(os.getenv("ASSORTMENT_RADAR_TOP_NEW", "30"))
RADAR_TOP_OPPORTUNITIES = int(os.getenv("ASSORTMENT_RADAR_TOP_OPPORTUNITIES", "20"))
RADAR_CACHE_SEC = int(os.getenv("ASSORTMENT_RADAR_CACHE_SEC", "900"))


def radar_page_size() -> int:
    """FastMoss goods API accepts pagesize <= 10; larger values return HTTP 400 Bad Request."""
    raw = os.getenv("ASSORTMENT_RADAR_PAGE_SIZE", str(FASTMOSS_GOODS_MAX_PAGE_SIZE))
    try:
        size = int(raw)
    except ValueError:
        size = FASTMOSS_GOODS_MAX_PAGE_SIZE
    return max(1, min(size, FASTMOSS_GOODS_MAX_PAGE_SIZE))
