"""Persisted Seller Level Analysis Update Data completion state."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("seller.intelligence.sla_update_state")

DEFAULT_STATE_PATH = Path(
    os.getenv("SLA_UPDATE_STATE_PATH", "data/seller_level_update_state.json")
)


def sla_update_state_path(path: Path | None = None) -> Path:
    return path or DEFAULT_STATE_PATH


def _mapping_summary(result: dict[str, Any]) -> dict[str, Any]:
    mapping = result.get("mapping") or {}
    summary = mapping.get("summary")
    if isinstance(summary, dict):
        return summary
    return {}


def build_snapshot_from_completion(
    *,
    result: dict[str, Any],
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serializable record written after a successful Update Data run."""
    mapping = result.get("mapping") or {}
    summary = _mapping_summary(result)
    status = status or {}
    refreshed_at = result.get("refreshed_at") or status.get("refreshed_at")
    finished_at = status.get("finished_at") or refreshed_at

    return {
        "version": 1,
        "completed": True,
        "refreshed_at": refreshed_at,
        "finished_at": finished_at,
        "percent": float(status.get("percent") if status.get("percent") is not None else 100),
        "shops_processed": status.get("shops_processed", summary.get("total")),
        "shops_total": status.get("shops_total", summary.get("total")),
        "newly_mapped_count": status.get(
            "newly_mapped_count", mapping.get("newly_mapped_count", 0)
        ),
        "pending_review_count": status.get(
            "pending_review_count", summary.get("need_review", mapping.get("pending_review_count"))
        ),
        "still_not_found_count": status.get(
            "still_not_found_count",
            summary.get("not_found", mapping.get("still_not_found_count")),
        ),
        "failed_count": status.get("failed_count", mapping.get("failed_count", 0)),
        "preserved_mapped_count": status.get(
            "preserved_mapped_count", mapping.get("preserved_mapped_count", 0)
        ),
        "changed_tiktok_count": status.get(
            "changed_tiktok_count", mapping.get("changed_tiktok_count", 0)
        ),
        "fastmoss_mapped_count": summary.get("mapped"),
        "mapping_summary": summary,
        "result": result,
        "status": {
            "step_label": status.get("step_label") or "Completed",
            "percent": float(status.get("percent") if status.get("percent") is not None else 100),
            "shops_processed": status.get("shops_processed", summary.get("total")),
            "shops_total": status.get("shops_total", summary.get("total")),
            "newly_mapped_count": status.get(
                "newly_mapped_count", mapping.get("newly_mapped_count", 0)
            ),
            "pending_review_count": status.get(
                "pending_review_count", summary.get("need_review")
            ),
            "still_not_found_count": status.get(
                "still_not_found_count", summary.get("not_found")
            ),
            "failed_count": status.get("failed_count", mapping.get("failed_count", 0)),
            "refreshed_at": refreshed_at,
            "finished_at": finished_at,
        },
    }


def save_sla_update_state(
    snapshot: dict[str, Any],
    path: Path | None = None,
) -> Path:
    target = sla_update_state_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    logger.info("SLA update state saved to %s", target.resolve())
    return target.resolve()


def load_sla_update_state(path: Path | None = None) -> dict[str, Any] | None:
    target = sla_update_state_path(path)
    if not target.is_file():
        return None
    try:
        with target.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read SLA update state from %s: %s", target, exc)
        return None


def snapshot_to_refresh_status(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Shape compatible with GET /business/refresh-status and frontend progress UI."""
    result = snapshot.get("result") or {}
    summary = snapshot.get("mapping_summary") or _mapping_summary(result)
    status = snapshot.get("status") or {}
    return {
        "running": False,
        "persisted": True,
        "step_id": "completed",
        "step_label": status.get("step_label") or "Completed",
        "step_index": 8,
        "step_count": 8,
        "percent": float(snapshot.get("percent", 100)),
        "shops_processed": snapshot.get("shops_processed", summary.get("total", 0)),
        "shops_total": snapshot.get("shops_total", summary.get("total", 0)),
        "newly_mapped_count": snapshot.get("newly_mapped_count", 0),
        "pending_review_count": snapshot.get("pending_review_count", summary.get("need_review", 0)),
        "still_not_found_count": snapshot.get("still_not_found_count", summary.get("not_found", 0)),
        "failed_count": snapshot.get("failed_count", 0),
        "preserved_mapped_count": snapshot.get("preserved_mapped_count", 0),
        "changed_tiktok_count": snapshot.get("changed_tiktok_count", 0),
        "elapsed_sec": status.get("elapsed_sec", 0),
        "started_at": None,
        "finished_at": snapshot.get("finished_at"),
        "refreshed_at": snapshot.get("refreshed_at"),
        "error": None,
        "failed_step_id": None,
        "failed_step_label": None,
        "result": result,
        "steps": [],
    }


def get_sla_update_state_for_api(path: Path | None = None) -> dict[str, Any]:
    """Payload for GET /business — last completed update (no rerun)."""
    snapshot = load_sla_update_state(path)
    if not snapshot or not snapshot.get("completed"):
        return {
            "completed": False,
            "loaded": False,
            "state_file": str(sla_update_state_path(path)),
        }

    refreshed_at = snapshot.get("refreshed_at") or snapshot.get("finished_at") or "—"
    summary = snapshot.get("mapping_summary") or {}
    return {
        "completed": True,
        "loaded": True,
        "state_file": str(sla_update_state_path(path)),
        "refreshed_at": refreshed_at,
        "finished_at": snapshot.get("finished_at"),
        "display_line": f"Last update completed at: {refreshed_at}",
        "percent": snapshot.get("percent", 100),
        "shops_processed": snapshot.get("shops_processed"),
        "shops_total": snapshot.get("shops_total"),
        "newly_mapped_count": snapshot.get("newly_mapped_count"),
        "pending_review_count": snapshot.get("pending_review_count"),
        "still_not_found_count": snapshot.get("still_not_found_count"),
        "failed_count": snapshot.get("failed_count"),
        "fastmoss_mapped_count": snapshot.get("fastmoss_mapped_count", summary.get("mapped")),
        "mapping_summary": summary,
        "result": snapshot.get("result"),
        "status": snapshot.get("status"),
    }


def persist_sla_update_completion(
    result: dict[str, Any],
    status: dict[str, Any] | None = None,
    *,
    path: Path | None = None,
) -> Path | None:
    if not result or not result.get("success"):
        return None
    snapshot = build_snapshot_from_completion(result=result, status=status)
    return save_sla_update_state(snapshot, path)
