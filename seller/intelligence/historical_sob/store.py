"""Persistent cache for FastMoss May/June TikTok historical GMV."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("seller.intelligence.historical_sob.store")

DEFAULT_CACHE_PATH = Path(
    os.getenv("HISTORICAL_SOB_CACHE_PATH", "historical_sob_cache.json")
)
# Committed seed — never overwritten at runtime. Used when the writable cache is
# missing or was wiped by a failed Railway re-fetch.
SEED_CACHE_PATH = Path(
    os.getenv("HISTORICAL_SOB_SEED_PATH", "historical_sob_cache.seed.json")
)

CACHE_VERSION = 2
PERIOD_KEY = "2026-05_2026-06"
HISTORICAL_PERIODS = {
    "may": {"start": "2026-05-01", "end": "2026-05-31", "shopee_multiplier": 1},
    "june": {"start": "2026-06-01", "end": "2026-06-30", "shopee_multiplier": 1},
}


def _empty_payload() -> dict[str, Any]:
    return {
        "version": CACHE_VERSION,
        "period_key": PERIOD_KEY,
        "updated_at": None,
        "shops": {},
    }


def _success_count(payload: dict[str, Any] | None) -> int:
    if not isinstance(payload, dict):
        return 0
    shops = payload.get("shops") or {}
    return sum(
        1
        for row in shops.values()
        if isinstance(row, dict)
        and row.get("status") == "success"
        and row.get("may_gmv_php") is not None
        and row.get("june_gmv_php") is not None
    )


def _read_cache_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read Historical SOB cache %s: %s", path, exc)
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("period_key") != PERIOD_KEY:
        return None
    if int(payload.get("version") or 0) < CACHE_VERSION:
        return None
    return payload


def cache_is_usable(payload: dict[str, Any] | None) -> bool:
    return _success_count(payload) > 0


def load_historical_sob_cache(path: Path | None = None) -> dict[str, Any]:
    """
    Load May/June TikTok GMV cache.

    Prefer the writable runtime file; if it is missing or has zero successful
    rows (e.g. a failed force-refresh wiped Railway disk), fall back to the
    committed seed so the UI keeps working without daily re-scrapes.
    """
    target = path or DEFAULT_CACHE_PATH
    runtime = _read_cache_file(target)
    if cache_is_usable(runtime):
        return runtime  # type: ignore[return-value]

    seed = _read_cache_file(SEED_CACHE_PATH)
    if cache_is_usable(seed):
        logger.info(
            "Historical SOB runtime cache unusable (%s success) — using seed (%s success)",
            _success_count(runtime),
            _success_count(seed),
        )
        hydrated = {
            "version": CACHE_VERSION,
            "period_key": PERIOD_KEY,
            "updated_at": seed.get("updated_at"),
            "shops": dict(seed.get("shops") or {}),
        }
        try:
            save_historical_sob_cache(hydrated, target)
        except OSError as exc:
            logger.warning("Could not hydrate Historical SOB cache from seed: %s", exc)
        return hydrated

    return runtime if isinstance(runtime, dict) else _empty_payload()


def save_historical_sob_cache(payload: dict[str, Any], path: Path | None = None) -> Path:
    target = path or DEFAULT_CACHE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload["version"] = CACHE_VERSION
    payload["period_key"] = PERIOD_KEY
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
    """Lookup cached May/June TikTok GMV by shop_id or normalized TikTok shop name."""
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
