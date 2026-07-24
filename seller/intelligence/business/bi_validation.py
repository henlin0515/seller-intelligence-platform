"""Validate FastMoss TikTok BI freshness for every approved SLA shop."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from seller.intelligence.business.collector import (
    STATUS_INVALID_RESPONSE,
    STATUS_MISSING_ID,
    STATUS_SUCCESS,
    row_is_fresh_success,
)
from seller.intelligence.business_time import business_today
from seller.intelligence.periods import IntelligencePeriods, resolve_periods


def _is_valid_number(value: Any) -> bool:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(n)


def validate_bi_sellers(
    sellers: list[dict[str, Any]],
    *,
    today: date | None = None,
    periods: IntelligencePeriods | None = None,
) -> dict[str, Any]:
    """
    Per-shop validation for Seller Level Analysis TikTok BI.

    A shop counts as fetch success only when:
    - fastmoss_shop_id present
    - status == success
    - data_date == today
    - MTD/M-1 ADGMV are finite numbers
    - period tags match current UI periods (when provided)
    """
    ref = today or business_today()
    current = periods or resolve_periods(ref)
    total = len(sellers)
    configured = 0
    missing_id = 0
    fetch_success = 0
    fetch_failed = 0
    stale = 0
    invalid_response = 0
    failures: list[dict[str, Any]] = []

    for row in sellers:
        if not isinstance(row, dict):
            continue
        shop_name = str(row.get("shop_name") or "")
        fm_id = str(row.get("fastmoss_shop_id") or "").strip()
        status = str(row.get("status") or "")
        http_status = row.get("http_status")
        error = str(row.get("error") or "")

        if not fm_id:
            missing_id += 1
            failures.append(
                {
                    "shop_name": shop_name,
                    "shop_id": row.get("shop_id"),
                    "fastmoss_shop_id": "",
                    "status": STATUS_MISSING_ID,
                    "http_status": http_status,
                    "error": error or "Missing fastmoss_shop_id",
                }
            )
            continue

        configured += 1
        url = str(row.get("fastmoss_shop_url") or "")
        url_ok = bool(fm_id) and (not url or fm_id in url)

        fresh = row_is_fresh_success(row, today=ref)
        mtd_ok = _is_valid_number(row.get("tiktok_mtd_adgmv_php"))
        m1_ok = _is_valid_number(row.get("tiktok_m1_adgmv_php"))
        mtd_gmv_ok = _is_valid_number(row.get("mtd_gmv_php"))
        m1_gmv_ok = _is_valid_number(row.get("m1_gmv_php"))
        periods_ok = True
        if current is not None:
            periods_ok = (
                str(row.get("mtd_start") or "") == current.mtd.start.isoformat()
                and str(row.get("mtd_end") or "") == current.mtd.end.isoformat()
                and str(row.get("m1_start") or "") == current.m1.start.isoformat()
                and str(row.get("m1_end") or "") == current.m1.end.isoformat()
            )

        if status == STATUS_SUCCESS and fresh and mtd_ok and m1_ok and mtd_gmv_ok and m1_gmv_ok and url_ok and periods_ok:
            fetch_success += 1
            continue

        if status == STATUS_SUCCESS and not fresh:
            stale += 1
            bucket = "STALE"
        elif status == STATUS_INVALID_RESPONSE or (
            status == STATUS_SUCCESS and (not mtd_ok or not m1_ok)
        ):
            invalid_response += 1
            bucket = STATUS_INVALID_RESPONSE
        else:
            fetch_failed += 1
            bucket = status or "FETCH_FAILED"

        failures.append(
            {
                "shop_name": shop_name,
                "shop_id": row.get("shop_id"),
                "fastmoss_shop_id": fm_id,
                "status": bucket,
                "http_status": http_status,
                "error": error
                or (
                    "stale data_date"
                    if bucket == "STALE"
                    else "invalid ADGMV"
                    if bucket == STATUS_INVALID_RESPONSE
                    else status
                ),
            }
        )

    all_success = (
        total > 0
        and fetch_success == total
        and missing_id == 0
        and fetch_failed == 0
        and stale == 0
        and invalid_response == 0
    )
    return {
        "today": ref.isoformat(),
        "total_shops": total,
        "configured_shops": configured,
        "missing_fastmoss_id": missing_id,
        "fetch_success": fetch_success,
        "fetch_failed": fetch_failed,
        "stale": stale,
        "invalid_response": invalid_response,
        "all_success": all_success,
        "success_label": (
            f"{fetch_success}/{total} SUCCESS"
            if total
            else "0/0 SUCCESS"
        ),
        "failed_label": f"{total - fetch_success} FAILED" if total else "0 FAILED",
        "failures": failures,
    }


def format_validation_summary(report: dict[str, Any]) -> str:
    lines = [
        f"Total shops: {report['total_shops']}",
        f"Configured shops: {report['configured_shops']}",
        f"Missing FastMoss ID: {report['missing_fastmoss_id']}",
        f"Fetch success: {report['fetch_success']}",
        f"Fetch failed: {report['fetch_failed']}",
        f"Stale: {report['stale']}",
        f"Invalid response: {report['invalid_response']}",
        "",
        report["success_label"],
        report["failed_label"],
    ]
    if report["failures"]:
        lines.append("")
        lines.append("Non-success shops:")
        for row in report["failures"]:
            lines.append(
                f"{row.get('shop_name') or '-'} | {row.get('fastmoss_shop_id') or '-'} | "
                f"{row.get('status')} | {row.get('http_status') if row.get('http_status') is not None else '-'} | "
                f"{row.get('error') or '-'}"
            )
    return "\n".join(lines)
