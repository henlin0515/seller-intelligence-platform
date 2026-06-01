"""Seller Intelligence V1 — shared configuration."""

from __future__ import annotations

import os

# Master currency: USD. TikTok / FastMoss source values are PHP.
USD_PHP_RATE: float = float(os.getenv("USD_PHP_RATE", "61.55"))
