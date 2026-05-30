from __future__ import annotations

# Matching weights (must sum to 1.0)
WEIGHT_IMAGE = 0.65
WEIGHT_TITLE = 0.25
WEIGHT_SKU = 0.10

# Classification thresholds (0–100 scale)
THRESHOLD_CONFIRMED = 90.0
THRESHOLD_NEED_REVIEW = 75.0

MATCH_CONFIRMED = "confirmed_match"
MATCH_NEED_REVIEW = "need_review"
MATCH_MISSING = "missing_product"

# Price gap bands
PRICE_GAP_GREEN_MAX = 5.0
PRICE_GAP_YELLOW_MAX = 15.0

PRICE_BAND_GREEN = "green"
PRICE_BAND_YELLOW = "yellow"
PRICE_BAND_RED = "red"

PLATFORM_SHOPEE = "shopee"
PLATFORM_TIKTOK = "tiktok"

TOP_PRODUCTS_FOR_PRICE_GAP = 10
NEW_LISTING_DAYS = 30
