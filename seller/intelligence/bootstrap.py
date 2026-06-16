"""Background intelligence data sync — keeps mapping/BI fresh without manual page refresh."""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("seller.intelligence.bootstrap")

_lock = threading.Lock()
_started = False


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        text = str(ts).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def intelligence_data_needs_sync() -> tuple[bool, str]:
    """Return (needs_sync, reason) using persisted mapping + SLA update state."""
    max_age_hours = float(os.getenv("INTELLIGENCE_SYNC_MAX_AGE_HOURS", "24"))

    try:
        from seller.fastmoss.mapping import DEFAULT_MAPPING_PATH, load_fastmoss_mapping
        from seller.intelligence.business.sla_update_state import load_sla_update_state
        from seller.intelligence.seller_master import get_seller_master
    except Exception as exc:
        return True, f"bootstrap import failed: {exc}"

    master = get_seller_master()
    master_count = len(master.sellers)

    try:
        mapping_payload = load_fastmoss_mapping(DEFAULT_MAPPING_PATH)
    except OSError:
        return True, "fastmoss_mapping.json missing"

    mappings = mapping_payload.get("mappings") or []
    if master_count and len(mappings) < max(1, int(master_count * 0.5)):
        return True, f"mapping rows ({len(mappings)}) << seller master ({master_count})"

    snapshot = load_sla_update_state()
    if not snapshot or not snapshot.get("completed"):
        return True, "no completed SLA update state"

    refreshed = _parse_iso(snapshot.get("refreshed_at") or snapshot.get("finished_at"))
    if refreshed is None:
        return True, "SLA update state has no refreshed_at"

    age_hours = (datetime.now(UTC) - refreshed).total_seconds() / 3600.0
    if age_hours > max_age_hours:
        return True, f"SLA data older than {max_age_hours:.0f}h ({age_hours:.1f}h)"

    generated = _parse_iso(str(mapping_payload.get("generated_at") or ""))
    if generated and (datetime.now(UTC) - generated).total_seconds() / 3600.0 > max_age_hours:
        return True, f"mapping file older than {max_age_hours:.0f}h"

    return False, "data fresh"


def run_intelligence_sync_job() -> dict[str, Any]:
    """Full sheet → FastMoss mapping → TikTok BI → Historical SOB pipeline."""
    from seller.intelligence.business.sla_refresh import run_sla_refresh_job

    logger.info("Intelligence background sync started")
    result = run_sla_refresh_job()
    logger.info("Intelligence background sync finished: success=%s", result.get("success"))
    return result


def maybe_start_background_sync() -> bool:
    """
    Start one background sync thread on startup when data is missing or stale.

    Controlled by INTELLIGENCE_AUTO_SYNC_ON_STARTUP (default true).
    """
    global _started
    if not _env_bool("INTELLIGENCE_AUTO_SYNC_ON_STARTUP", True):
        logger.info("Intelligence auto-sync on startup disabled")
        return False

    with _lock:
        if _started:
            return False
        _started = True

    needs, reason = intelligence_data_needs_sync()
    if not needs:
        logger.info("Intelligence bootstrap skipped: %s", reason)
        return False

    def _worker() -> None:
        time.sleep(float(os.getenv("INTELLIGENCE_BOOTSTRAP_DELAY_SEC", "3")))
        try:
            from seller.intelligence.business.sla_refresh import get_sla_refresh_status

            if get_sla_refresh_status().get("running"):
                logger.info("Intelligence bootstrap skipped: refresh already running")
                return
            run_intelligence_sync_job()
        except Exception:
            logger.exception("Intelligence background sync failed")

    threading.Thread(target=_worker, name="intelligence-bootstrap", daemon=True).start()
    logger.info("Intelligence background sync queued: %s", reason)
    return True
