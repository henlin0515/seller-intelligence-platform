"""
FastMoss data provider — documented endpoints used by this project.

Do not invent fields. Mapping below matches live `GET /api/shop/v3/recentData`
responses observed from the FastMoss web app (logged-in / anonymous JSON API).

If FastMoss issues a separate official partner API, fill the TODOs and point
``FASTMOSS_API_BASE_URL`` at that host without changing collectors.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Confirmed in-repo endpoint (web-app JSON API)
# ---------------------------------------------------------------------------
# Method: GET
# Path:   /api/shop/v3/recentData
# Query:  id=<fastmoss_shop_id>
#         start_date=YYYY-MM-DD
#         end_date=YYYY-MM-DD
#         region=PH
#         _time=<unix>
#         cnonce=<random>
# Auth:   optional Cookie (FASTMOSS_COOKIE) OR
#         Authorization: Bearer <FASTMOSS_ACCESS_TOKEN> OR
#         X-API-Key: <FASTMOSS_API_KEY>
#         Anonymous (no Cookie) often works for recentData.
# Response mapping (confirmed):
#   data.list.total_info.sale_amount  → period GMV (PHP)
#   data.list.total_info.shop_name    → FastMoss shop name
#   data.list.total_info.sold_count   → sales volume
# ADGMV = sale_amount / inclusive day count for the requested period.

RECENT_DATA_PATH = "/api/shop/v3/recentData"
RECENT_DATA_GMV_FIELD = ("data", "list", "total_info", "sale_amount")
RECENT_DATA_CURRENCY = "PHP"  # FastMoss PH market returns PHP in sale_amount

# ---------------------------------------------------------------------------
# Optional partner API placeholders (leave unset unless you have docs)
# ---------------------------------------------------------------------------
# TODO_FASTMOSS_ENDPOINT: partner base path if different from RECENT_DATA_PATH
# TODO_FASTMOSS_AUTH_FORMAT: e.g. "Bearer" / "X-API-Key" / "Cookie"
# TODO_FASTMOSS_RESPONSE_MAPPING: document field paths when partner docs arrive

TODO_FASTMOSS_ENDPOINT = None
TODO_FASTMOSS_AUTH_FORMAT = None
TODO_FASTMOSS_RESPONSE_MAPPING = None
