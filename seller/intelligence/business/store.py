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
SEED_BI_DATA_PATH = Path(
    os.getenv("BUSINESS_INTELLIGENCE_SEED_PATH", "business_intelligence_data.seed.json")
)

CACHE_STATUS_READY = "ready"
CACHE_STATUS_INVALIDATED = "invalidated"
CACHE_STATUS_REFRESHING = "refreshing"


def bi_data_path(path: Path | None = None) -> Path:
    return path or DEFAULT_BI_DATA_PATH


def _bi_success_count(payload: dict[str, Any] | None) -> int:
    if not isinstance(payload, dict):
        return 0
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if int(summary.get("success") or 0) > 0:
        return int(summary["success"])
    return sum(
        1
        for row in payload.get("sellers") or []
        if isinstance(row, dict) and row.get("status") == "success"
    )


def _read_bi_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read BI cache %s: %s", path, exc)
        return None
    return payload if isinstance(payload, dict) else None


def load_business_intelligence_data(
    path: Path | None = None,
) -> dict[str, Any] | None:
    """
    Load TikTok BI cache.

    Prefer the writable runtime file; if it is missing / empty / invalidated with
    zero successes, fall back to the committed seed so Railway keeps serving data.
    """
    target = bi_data_path(path)
    runtime = _read_bi_file(target)
    if runtime is not None and _bi_success_count(runtime) > 0:
        status = str(runtime.get("cache_status") or CACHE_STATUS_READY).lower()
        # Serve successful rows even while a background refresh is in progress.
        if status != CACHE_STATUS_INVALIDATED:
            return runtime

    seed = _read_bi_file(SEED_BI_DATA_PATH)
    if seed is not None and _bi_success_count(seed) > 0:
        logger.info(
            "BI runtime cache unusable (success=%s status=%s) — using seed (success=%s)",
            _bi_success_count(runtime),
            (runtime or {}).get("cache_status"),
            _bi_success_count(seed),
        )
        try:
            save_business_intelligence_data(seed, target)
        except OSError as exc:
            logger.warning("Could not hydrate BI cache from seed: %s", exc)
            return seed
        return _read_bi_file(target) or seed

    return runtime


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
    if status == CACHE_STATUS_INVALIDATED:
        return False
    # REFRESHING with successful sellers is still usable for UI (preserve ADGMV).
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
    preserve_sellers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Mark BI cache as refreshing/invalidated for current UI period tags.

    When ``preserve_sellers`` is provided (successful rows for matching periods),
    keep those ADGMV values so the UI does not flash empty / N/A mid-refresh.
    """
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    sellers = list(preserve_sellers or [])
    success = sum(1 for row in sellers if isinstance(row, dict) and row.get("status") == "success")
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
            "processed": len(sellers),
            "success": success,
            "failed": len(sellers) - success,
            "approved_only": True,
        },
        "sellers": sellers,
    }
    save_business_intelligence_data(payload, path)
    logger.warning(
        "BI cache invalidated | status=%s | reason=%s | trigger=%s | preserved=%s | mtd=%s→%s | m1=%s→%s",
        cache_status,
        reason,
        trigger,
        success,
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
