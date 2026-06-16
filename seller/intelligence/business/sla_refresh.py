"""Seller Level Analysis — background Update Data job with progress tracking."""

from __future__ import annotations

import logging
import threading
import time
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

from seller.fastmoss.mapping import (
    MAPPING_MAPPED,
    MAPPING_NEED_REVIEW,
    MAPPING_NOT_FOUND,
    _merge_mapping_row,
    _summary_counts,
    load_fastmoss_mapping,
    map_seller_to_fastmoss,
    needs_fastmoss_rematch,
    save_fastmoss_mapping,
)
from seller.fastmoss.review import review_summary, sync_reviews_from_mappings
from seller.intelligence.business.collector import collect_mapped_shop_tiktok
from seller.intelligence.business.shopee_adgmv import clear_shopee_adgmv_cache, get_shopee_adgmv
from seller.intelligence.business.store import (
    fastmoss_collection_by_shop_id,
    load_business_intelligence_data,
    save_business_intelligence_data,
)
from seller.intelligence.config import USD_PHP_RATE
from seller.intelligence.periods import resolve_periods
from seller.intelligence.seller_master import (
    clear_seller_master_cache,
    get_seller_master,
)
from seller.fastmoss.review import approved_mapping_rows

logger = logging.getLogger("seller.intelligence.sla_refresh")

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "step_id": None,
    "step_label": None,
    "step_index": 0,
    "step_count": 9,
    "percent": 0,
    "shops_processed": 0,
    "shops_total": 0,
    "newly_mapped_count": 0,
    "pending_review_count": 0,
    "still_not_found_count": 0,
    "failed_count": 0,
    "preserved_mapped_count": 0,
    "changed_tiktok_count": 0,
    "elapsed_sec": 0,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "failed_step_id": None,
    "failed_step_label": None,
    "result": None,
}

STEPS: list[tuple[str, str]] = [
    ("seller_master", "Reloading seller master from shpoee link"),
    ("check_names", "Checking new / changed TikTok shop names"),
    ("rematch_not_found", "Rematching NOT_FOUND shops"),
    ("rematch_pending", "Rematching pending review shops"),
    ("preserve_mapped", "Preserving existing MAPPED shops"),
    ("save_mapping", "Updating FastMoss mapping storage"),
    ("reload_sla", "Reloading Seller Level Analysis data"),
    ("historical_sob", "Refreshing Historical SOB"),
    ("completed", "Completed"),
]

_STEP_INDEX = {step_id: idx for idx, (step_id, _) in enumerate(STEPS)}


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def get_sla_refresh_status() -> dict[str, Any]:
    with _lock:
        out = deepcopy(_state)
    out["steps"] = [{"id": s[0], "label": s[1]} for s in STEPS]
    if out.get("running"):
        return out
    if out.get("result"):
        return out
    from seller.intelligence.business.sla_update_state import (
        load_sla_update_state,
        snapshot_to_refresh_status,
    )

    persisted = load_sla_update_state()
    if persisted and persisted.get("completed"):
        merged = snapshot_to_refresh_status(persisted)
        merged["steps"] = out["steps"]
        return merged
    return out


def _set_state(**kwargs: Any) -> None:
    with _lock:
        _state.update(kwargs)
        started = _state.get("_started_monotonic")
        if started:
            _state["elapsed_sec"] = round(time.time() - started, 1)


def _fail(step_id: str, message: str) -> None:
    idx = _STEP_INDEX.get(step_id, 0)
    label = STEPS[idx][1] if idx < len(STEPS) else step_id
    _set_state(
        running=False,
        error=message,
        failed_step_id=step_id,
        failed_step_label=label,
        finished_at=_utc_now(),
    )


def _percent_for(step_id: str, *, sub: float = 0.0) -> float:
    idx = _STEP_INDEX.get(step_id, 0)
    base = (idx / len(STEPS)) * 100.0
    span = 100.0 / len(STEPS)
    return min(99.0, round(base + sub * span, 1))


def _begin_step(step_id: str, *, shops_total: int | None = None, sub: float = 0.0) -> None:
    idx = _STEP_INDEX[step_id]
    label = STEPS[idx][1]
    patch: dict[str, Any] = {
        "step_id": step_id,
        "step_label": label,
        "step_index": idx + 1,
        "percent": _percent_for(step_id, sub=sub),
    }
    if shops_total is not None:
        patch["shops_total"] = shops_total
        patch["shops_processed"] = 0
    _set_state(**patch)


def _tick_shop(
    step_id: str,
    processed: int,
    total: int,
    *,
    counts: dict[str, Any] | None = None,
) -> None:
    sub = (processed / total) if total else 1.0
    patch: dict[str, Any] = {
        "shops_processed": processed,
        "shops_total": total,
        "percent": _percent_for(step_id, sub=sub),
    }
    if counts:
        patch.update(counts)
    _set_state(**patch)


def _categorize_sellers(
    master_sellers: list[Any],
    existing_by_shop: dict[str, dict[str, Any]],
) -> tuple[list[tuple[Any, dict[str, Any] | None]], list[tuple[Any, dict[str, Any] | None]], int, int]:
    """Return (not_found_queue, need_review_queue, preserved_mapped, changed_tiktok)."""
    not_found_q: list[tuple[Any, dict[str, Any] | None]] = []
    pending_q: list[tuple[Any, dict[str, Any] | None]] = []
    preserved = 0
    changed = 0

    for seller in master_sellers:
        existing = existing_by_shop.get(seller.shop_id)
        cur = str(seller.tiktok_shop_name or "").strip()
        prev = str((existing or {}).get("tiktok_shop_name") or "").strip()
        if existing and cur != prev:
            changed += 1

        if existing and existing.get("manual_override"):
            preserved += 1
            continue

        status = str((existing or {}).get("mapping_status") or MAPPING_NOT_FOUND).upper()
        if status == MAPPING_MAPPED:
            if cur != prev or needs_fastmoss_rematch(existing, seller):
                not_found_q.append((seller, existing))
            else:
                preserved += 1
        elif status == MAPPING_NEED_REVIEW:
            pending_q.append((seller, existing))
        else:
            not_found_q.append((seller, existing))

    return not_found_q, pending_q, preserved, changed


def _rematch_queue(
    queue: list[tuple[Any, dict[str, Any] | None]],
    mappings_by_id: dict[str, dict[str, Any]],
    *,
    step_id: str,
    delay_sec: float,
    counts: dict[str, int],
) -> None:
    total = len(queue)
    _begin_step(step_id, shops_total=total)
    failed = counts.get("failed_count", 0)
    newly = counts.get("newly_mapped_count", 0)

    for i, (seller, existing) in enumerate(queue, start=1):
        if i > 1 and delay_sec > 0:
            time.sleep(delay_sec)
        prior = str((existing or {}).get("mapping_status") or MAPPING_NOT_FOUND).upper()
        try:
            new_row = map_seller_to_fastmoss(seller)
            row = _merge_mapping_row(existing, new_row)
        except Exception as exc:
            logger.warning("FastMoss rematch failed for %s: %s", seller.shop_id, exc)
            failed += 1
            row = existing or {
                "shop_id": seller.shop_id,
                "shop_name": seller.shop_name,
                "tiktok_shop_name": seller.tiktok_shop_name,
                "mapping_status": MAPPING_NOT_FOUND,
                "confidence": 0.0,
            }
        mappings_by_id[seller.shop_id] = row
        new_status = str(row.get("mapping_status") or "").upper()
        if new_status == MAPPING_MAPPED and prior != MAPPING_MAPPED:
            newly += 1

        summary = _summary_counts(list(mappings_by_id.values()))
        _tick_shop(
            step_id,
            i,
            total,
            counts={
                "failed_count": failed,
                "newly_mapped_count": newly,
                "pending_review_count": summary["need_review"],
                "still_not_found_count": summary["not_found"],
            },
        )

    counts["failed_count"] = failed
    counts["newly_mapped_count"] = newly


def run_sla_refresh_job() -> dict[str, Any]:
    """Run full SLA Update Data pipeline (blocking — call from worker thread)."""
    from seller.fastmoss.mapping import REQUEST_DELAY_SEC

    delay_sec = REQUEST_DELAY_SEC
    counts = {
        "newly_mapped_count": 0,
        "failed_count": 0,
    }

    try:
        _begin_step("seller_master")
        from seller.intelligence.gp_shop_rm import clear_gp_shop_rm_cache

        clear_seller_master_cache()
        clear_shopee_adgmv_cache()
        clear_gp_shop_rm_cache()
        master = get_seller_master(force_refresh=True)
        get_shopee_adgmv(force_refresh=True)
        _set_state(shops_total=len(master.sellers), shops_processed=len(master.sellers))

        _begin_step("check_names")
        target = Path("fastmoss_mapping.json")
        try:
            existing_payload = load_fastmoss_mapping(target)
        except OSError:
            existing_payload = {"mappings": []}
        existing_by_shop: dict[str, dict[str, Any]] = {}
        for row in existing_payload.get("mappings") or []:
            if isinstance(row, dict) and row.get("shop_id"):
                existing_by_shop[str(row["shop_id"])] = row

        not_found_q, pending_q, preserved, changed = _categorize_sellers(
            master.sellers, existing_by_shop
        )
        _set_state(changed_tiktok_count=changed, preserved_mapped_count=preserved)

        mappings_by_id: dict[str, dict[str, Any]] = {}
        for seller in master.sellers:
            existing = existing_by_shop.get(seller.shop_id)
            if not existing:
                continue
            status = str(existing.get("mapping_status") or "").upper()
            if existing.get("manual_override") or (
                status == MAPPING_MAPPED
                and str(seller.tiktok_shop_name or "").strip()
                == str(existing.get("tiktok_shop_name") or "").strip()
            ):
                mappings_by_id[seller.shop_id] = existing

        _begin_step("preserve_mapped")
        _set_state(
            preserved_mapped_count=preserved,
            shops_processed=preserved,
            shops_total=len(master.sellers),
            percent=_percent_for("preserve_mapped", sub=1.0),
        )

        _rematch_queue(
            not_found_q,
            mappings_by_id,
            step_id="rematch_not_found",
            delay_sec=delay_sec,
            counts=counts,
        )
        _rematch_queue(
            pending_q,
            mappings_by_id,
            step_id="rematch_pending",
            delay_sec=delay_sec,
            counts=counts,
        )

        for seller in master.sellers:
            if seller.shop_id not in mappings_by_id:
                mappings_by_id[seller.shop_id] = existing_by_shop.get(
                    seller.shop_id,
                    {
                        "shop_id": seller.shop_id,
                        "shop_name": seller.shop_name,
                        "tiktok_shop_name": seller.tiktok_shop_name,
                        "mapping_status": MAPPING_NOT_FOUND,
                        "confidence": 0.0,
                    },
                )

        mappings = [mappings_by_id[s.shop_id] for s in master.sellers if s.shop_id in mappings_by_id]

        _begin_step("save_mapping")
        summary = _summary_counts(mappings)
        mapping_payload = {
            "generated_at": _utc_now(),
            "region": "PH",
            "source": "seller_master_google_sheet",
            "summary": summary,
            "mappings": mappings,
        }
        save_fastmoss_mapping(mapping_payload, target)
        sync_reviews_from_mappings(mappings)
        _set_state(
            pending_review_count=summary["need_review"],
            still_not_found_count=summary["not_found"],
            percent=_percent_for("save_mapping", sub=1.0),
        )

        _begin_step("reload_sla")
        today = date.today()
        periods = resolve_periods(today)
        approved = approved_mapping_rows()
        total_bi = len(approved)
        bi_failed = 0
        bi_refreshed = 0
        bi_data = load_business_intelligence_data() or {
            "reference_today": today.isoformat(),
            "periods": periods.as_dict(),
            "usd_php_rate": USD_PHP_RATE,
            "source": "fastmoss_recentData",
            "sellers": [],
        }
        approved_ids = {str(r.get("shop_id")) for r in approved}
        collection_by_shop = {
            sid: row
            for sid, row in fastmoss_collection_by_shop_id(bi_data).items()
            if sid in approved_ids
        }

        for index, row in enumerate(approved, start=1):
            shop_id = str(row.get("shop_id") or "")
            if not shop_id:
                continue
            if index > 1 and delay_sec > 0:
                time.sleep(delay_sec)
            try:
                collected = collect_mapped_shop_tiktok(row, periods, delay_sec=0)
            except Exception as exc:
                logger.warning("TikTok BI collect failed for %s: %s", shop_id, exc)
                bi_failed += 1
                counts["failed_count"] = counts.get("failed_count", 0) + 1
                continue
            collection_by_shop[shop_id] = collected
            if collected.get("status") == "success":
                bi_refreshed += 1
            else:
                bi_failed += 1
            _tick_shop(
                "reload_sla",
                index,
                total_bi,
                counts={
                    "failed_count": counts["failed_count"] + bi_failed,
                },
            )

        sellers_list = list(collection_by_shop.values())
        success = sum(1 for r in sellers_list if r.get("status") == "success")
        bi_data.update(
            {
                "generated_at": _utc_now(),
                "reference_today": today.isoformat(),
                "periods": periods.as_dict(),
                "usd_php_rate": USD_PHP_RATE,
                "source": "fastmoss_recentData",
                "summary": {
                    "processed": len(sellers_list),
                    "success": success,
                    "failed": len(sellers_list) - success,
                    "approved_only": True,
                },
                "sellers": sellers_list,
            }
        )
        save_business_intelligence_data(bi_data)

        _begin_step("historical_sob")
        historical_sob_result: dict[str, Any] = {}
        try:
            from seller.intelligence.historical_sob import refresh_historical_sob

            historical_sob_result = refresh_historical_sob(force=True)
            _set_state(percent=_percent_for("historical_sob", sub=1.0))
        except Exception as exc:
            logger.warning("Historical SOB refresh during SLA update failed: %s", exc)
            historical_sob_result = {"success": False, "error": str(exc)}

        review = review_summary()
        refreshed_at = _utc_now()
        result = {
            "success": True,
            "refreshed_at": refreshed_at,
            "mapping": {
                "summary": summary,
                "newly_mapped_count": counts["newly_mapped_count"],
                "still_not_found_count": summary["not_found"],
                "pending_review_count": summary["need_review"],
                "failed_count": counts["failed_count"],
                "preserved_mapped_count": preserved,
                "changed_tiktok_count": changed,
            },
            "review": review,
            "tiktok_bi": {
                "tiktok_data_refreshed_count": bi_refreshed,
                "collection_success": success,
                "failed_count": bi_failed,
            },
            "historical_sob": historical_sob_result,
            "completion_message": (
                f"FastMoss mapped: {summary['mapped']} · "
                f"Pending review: {summary['need_review']} · "
                f"Not found: {summary['not_found']} · "
                f"Newly mapped: {counts['newly_mapped_count']}"
            ),
        }

        final_status = {
            "step_id": "completed",
            "step_label": STEPS[-1][1],
            "step_index": len(STEPS),
            "percent": 100.0,
            "running": False,
            "finished_at": refreshed_at,
            "shops_processed": summary.get("total"),
            "shops_total": summary.get("total"),
            "pending_review_count": summary["need_review"],
            "still_not_found_count": summary["not_found"],
            "newly_mapped_count": counts["newly_mapped_count"],
            "failed_count": counts["failed_count"],
            "preserved_mapped_count": preserved,
            "changed_tiktok_count": changed,
            "refreshed_at": refreshed_at,
        }
        _set_state(
            error=None,
            failed_step_id=None,
            failed_step_label=None,
            result=result,
            **{k: v for k, v in final_status.items() if k != "running"},
        )
        from seller.intelligence.business.sla_update_state import persist_sla_update_completion

        persist_sla_update_completion(result, final_status)
        return result
    except Exception as exc:
        logger.exception("SLA refresh job failed")
        step_id = _state.get("step_id") or "seller_master"
        _fail(step_id, str(exc))
        raise


def start_sla_refresh_background() -> dict[str, Any]:
    with _lock:
        if _state.get("running"):
            return {"started": False, "reason": "already_running", **get_sla_refresh_status()}

    def _worker() -> None:
        global _state
        with _lock:
            _state = {
                "running": True,
                "step_id": STEPS[0][0],
                "step_label": STEPS[0][1],
                "step_index": 1,
                "step_count": len(STEPS),
                "percent": 0,
                "shops_processed": 0,
                "shops_total": 0,
                "newly_mapped_count": 0,
                "pending_review_count": 0,
                "still_not_found_count": 0,
                "failed_count": 0,
                "preserved_mapped_count": 0,
                "changed_tiktok_count": 0,
                "elapsed_sec": 0,
                "started_at": _utc_now(),
                "finished_at": None,
                "error": None,
                "failed_step_id": None,
                "failed_step_label": None,
                "result": None,
                "_started_monotonic": time.time(),
            }
        try:
            run_sla_refresh_job()
        except Exception:
            pass

    threading.Thread(target=_worker, name="sla-refresh", daemon=True).start()
    return {"started": True, **get_sla_refresh_status()}
