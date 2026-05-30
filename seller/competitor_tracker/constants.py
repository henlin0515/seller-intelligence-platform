from __future__ import annotations

import os

COMPETITOR_TAB_NAME = "COMPETITOR_TRACKER"
MAX_SHOPS_PER_RUN = 50
DEFAULT_DELAY_SEC = float(os.getenv("COMPETITOR_CHECK_DELAY_SEC", "2.0"))
FETCH_TIMEOUT_SEC = float(os.getenv("COMPETITOR_FETCH_TIMEOUT_SEC", "20"))

VOUCHER_KEYWORDS = (
    # English
    "voucher",
    "coupon",
    "discount",
    " off",
    "free shipping",
    "shop voucher",
    "min spend",
    # Filipino
    "diskwento",
    "libreng shipping",
    # Chinese (simplified + traditional)
    "优惠券",
    "優惠券",
    "折扣",
    "免运",
    "免運",
)

VOUCHER_PATTERNS = (
    r"(?:₱|php)\s*\d+",
    r"\d+\s*%\s*off",
    r"\b\d+%\b",
    r"\boff\b",
    r"min\.?\s*spend",
    r"free\s*shipping",
)
