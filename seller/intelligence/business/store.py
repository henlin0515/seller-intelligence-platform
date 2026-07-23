"""Business Intelligence V1 — persisted FastMoss TikTok collection (atomic cache)."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from seller.intelligence.config import USD_PHP_RATE
from seller.intelligence.periods import IntelligencePeriods, periods_match_payload

logger = logging.getLogger("seller.intelligence.business.store")

DEFAULT_BI_DATA_PATH = Path(
    os.getenv("BUSINESS_INTELLIGENCE_DATA_PATH", "business_intelligence_data.json")
)

CACHE_STATUS_READY = "ready"
CACHE_STATUS_INVALIDATED = "invalidated"
CACHE_STATUS_REFRESHING = "refreshing"


def bi_data_path(path: Path | None = None) -> Path:
    return path or DEFAULT_BI_DATA_PATH


def load_business_intelligence_data(
    path: Path | None = None,
) -> dict[str, Any] | None:
    target = bi_data_path(path)
    if not target.is_file():
        return None
    with target.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_business_intelligence_data(
    payload: dict[str, Any],
    path: Path | None = None,
) -> Path:
    """Atomically overwrite BI cache (temp file + replace)."""
    target = bi_data_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, target)
    return target.resolve()


def bi_cache_usable_for_periods(
    saved: dict[str, Any] | None,
    current: IntelligencePeriods,
) -> bool:
    """True when BI JSON has successful collects for the current UI MTD/M-1 tags."""
    if not isinstance(saved, dict):
        return False
    status = str(saved.get("cache_status") or CACHE_STATUS_READY).lower()
    if status in {CACHE_STATUS_INVALIDATED, CACHE_STATUS_REFRESHING}:
        return False
    periods = saved.get("periods")
    if not periods_match_payload(
        periods if isinstance(periods, dict) else None,
        current,
    ):
        return False
    summary = saved.get("summary") if isinstance(saved.get("summary"), dict) else {}
    if int(summary.get("success") or 0) <= 0:
        return False
    return True


def invalidate_business_intelligence_cache(
    periods: IntelligencePeriods,
    *,
    reason: str,
    trigger: str = "period_change",
    path: Path | None = None,
    cache_status: str = CACHE_STATUS_INVALIDATED,
) -> dict[str, Any]:
    """
    Drop stale TikTok rows immediately so the UI never serves wrong-period ADGMV.

    Writes a placeholder payload aligned to the current UI period tags (empty sellers).
    """
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload = {
        "generated_at": now,
        "reference_today": periods.reference_today.isoformat(),
        "periods": periods.as_dict(),
        "usd_php_rate": USD_PHP_RATE,
        "source": "fastmoss_recentData",
        "cache_status": cache_status,
        "invalidated_at": now,
        "invalidated_reason": reason,
        "invalidated_trigger": trigger,
        "summary": {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "approved_only": True,
        },
        "sellers": [],
    }
    save_business_intelligence_data(payload, path)
    logger.warning(
        "BI cache invalidated | status=%s | reason=%s | trigger=%s | mtd=%s→%s | m1=%s→%s",
        cache_status,
        reason,
        trigger,
        periods.mtd.start.isoformat(),
        periods.mtd.end.isoformat(),
        periods.m1.start.isoformat(),
        periods.m1.end.isoformat(),
    )
    return payload


def tiktok_inputs_by_shop_id(
    data: dict[str, Any] | None,
) -> dict[str, dict[str, float]]:
    """Map shop_id -> TikTok ADGMV PHP inputs from saved collection."""
    return {
        shop_id: {
            "tiktok_mtd_adgmv_php": float(row.get("tiktok_mtd_adgmv_php") or 0),
            "tiktok_m1_adgmv_php": float(row.get("tiktok_m1_adgmv_php") or 0),
        }
        for shop_id, row in fastmoss_collection_by_shop_id(data).items()
        if row.get("status") == "success"
    }


def fastmoss_collection_by_shop_id(
    data: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Map shop_id -> full FastMoss collection row."""
    if not data:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in data.get("sellers") or []:
        if not isinstance(row, dict):
            continue
        shop_id = str(row.get("shop_id") or "").strip()
        if shop_id:
            out[shop_id] = row
    return out
