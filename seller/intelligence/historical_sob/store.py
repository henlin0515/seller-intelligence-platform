"""Persistent cache for FastMoss April/May TikTok historical GMV."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

DEFAULT_CACHE_PATH = Path(
    os.getenv("HISTORICAL_SOB_CACHE_PATH", "historical_sob_cache.json")
)


def load_historical_sob_cache(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_CACHE_PATH
    if not target.is_file():
        return {"version": 1, "updated_at": None, "shops": {}}
    with target.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_historical_sob_cache(payload: dict[str, Any], path: Path | None = None) -> Path:
    target = path or DEFAULT_CACHE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload["version"] = 1
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return target.resolve()


def shop_tiktok_cache_row(cache: dict[str, Any], shop_id: str) -> dict[str, Any] | None:
    row = (cache.get("shops") or {}).get(str(shop_id))
    return dict(row) if isinstance(row, dict) else None


def resolve_tiktok_cache_row(
    cache: dict[str, Any],
    *,
    shop_id: str,
    tiktok_shop_name: str = "",
) -> dict[str, Any] | None:
    """Lookup cached April/May TikTok GMV by shop_id or normalized TikTok shop name."""
    from seller.intelligence.gp_shop_rm import normalize_shop_key

    shops = cache.get("shops") or {}
    sid = str(shop_id or "").strip()
    if sid:
        row = shops.get(sid)
        if isinstance(row, dict):
            return dict(row)
    key = normalize_shop_key(tiktok_shop_name)
    if key:
        for row in shops.values():
            if not isinstance(row, dict):
                continue
            if normalize_shop_key(str(row.get("tiktok_shop_name") or "")) == key:
                return dict(row)
    return None
