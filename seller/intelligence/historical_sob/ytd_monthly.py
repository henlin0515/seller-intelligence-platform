"""YTD monthly Shopee ADGMV from Google Sheet tab ``ytd monthly data``."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from seller.google_sheets.client import get_sheets_client
from seller.google_sheets.config import is_configured
from seller.google_sheets.exceptions import GoogleSheetsNotConfiguredError

logger = logging.getLogger("seller.intelligence.historical_sob.ytd_monthly")

DEFAULT_YTD_MONTHLY_TAB = "ytd monthly data"

APRIL_DAY_COUNT = 30
MAY_DAY_COUNT = 31


@dataclass(frozen=True)
class YtdMonthlyRecord:
    shop_id: str
    shop_name: str
    ytd_apr_adgmv: float
    ytd_may_adgmv: float

    @property
    def april_shopee_gmv(self) -> float:
        return self.ytd_apr_adgmv * APRIL_DAY_COUNT

    @property
    def may_shopee_gmv(self) -> float:
        return self.ytd_may_adgmv * MAY_DAY_COUNT


@dataclass
class YtdMonthlyImportStats:
    total_rows_read: int = 0
    total_loaded: int = 0
    duplicate_shop_ids: list[str] = field(default_factory=list)
    skipped_rows: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_rows_read": self.total_rows_read,
            "total_loaded": self.total_loaded,
            "duplicate_shop_id_count": len(self.duplicate_shop_ids),
            "duplicate_shop_ids": self.duplicate_shop_ids,
            "skipped_row_count": len(self.skipped_rows),
            "skipped_rows": self.skipped_rows,
        }


@dataclass
class YtdMonthlyLoadResult:
    by_shop_id: dict[str, YtdMonthlyRecord]
    stats: YtdMonthlyImportStats
    tab: str
    data_source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "tab": self.tab,
            "data_source": self.data_source,
            "import": self.stats.as_dict(),
            "loaded_count": len(self.by_shop_id),
        }


_cache: YtdMonthlyLoadResult | None = None


def ytd_monthly_tab_name() -> str:
    return (os.getenv("GOOGLE_SHEET_YTD_MONTHLY_TAB") or DEFAULT_YTD_MONTHLY_TAB).strip()


def _cell(row: list[Any], index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _parse_float(value: str) -> float:
    text = (value or "").strip().replace(",", "")
    if not text:
        return 0.0
    return float(text)


def parse_ytd_monthly_rows(
    rows: list[list[Any]],
    *,
    tab: str = DEFAULT_YTD_MONTHLY_TAB,
) -> YtdMonthlyLoadResult:
    """Parse grid: shop_name, shop_id, ytd_apr_adgmv, ytd_may_adgmv (columns A–D)."""
    stats = YtdMonthlyImportStats()
    by_shop_id: dict[str, YtdMonthlyRecord] = {}

    if not rows:
        return YtdMonthlyLoadResult(by_shop_id, stats, tab=tab, data_source="google_sheet")

    for row_index, row in enumerate(rows[1:], start=2):
        stats.total_rows_read += 1
        shop_name = _cell(row, 0)
        shop_id = _cell(row, 1)
        if not shop_id:
            stats.skipped_rows.append({"row": row_index, "reason": "missing_shop_id"})
            continue

        if shop_id in by_shop_id:
            if shop_id not in stats.duplicate_shop_ids:
                stats.duplicate_shop_ids.append(shop_id)
            stats.skipped_rows.append(
                {"row": row_index, "reason": "duplicate_shop_id", "shop_id": shop_id}
            )
            continue

        try:
            record = YtdMonthlyRecord(
                shop_id=shop_id,
                shop_name=shop_name or shop_id,
                ytd_apr_adgmv=_parse_float(_cell(row, 2)),
                ytd_may_adgmv=_parse_float(_cell(row, 3)),
            )
        except ValueError as exc:
            stats.skipped_rows.append(
                {
                    "row": row_index,
                    "reason": "invalid_numeric_value",
                    "shop_id": shop_id,
                    "error": str(exc),
                }
            )
            continue

        by_shop_id[shop_id] = record

    stats.total_loaded = len(by_shop_id)
    return YtdMonthlyLoadResult(
        by_shop_id=by_shop_id,
        stats=stats,
        tab=tab,
        data_source="google_sheet",
    )


def load_ytd_monthly_from_sheet(*, force_refresh: bool = False) -> YtdMonthlyLoadResult:
    global _cache
    if _cache is not None and not force_refresh:
        return _cache

    if not is_configured():
        raise GoogleSheetsNotConfiguredError(
            "Google Sheets is not configured for YTD monthly import."
        )

    tab = ytd_monthly_tab_name()
    client = get_sheets_client()
    rows = client.fetch_worksheet_values(tab)
    result = parse_ytd_monthly_rows(rows, tab=tab)
    logger.info(
        "YTD monthly loaded from tab %r: %s shops (%s rows read)",
        tab,
        result.stats.total_loaded,
        result.stats.total_rows_read,
    )
    _cache = result
    return result


def get_ytd_monthly(*, force_refresh: bool = False) -> YtdMonthlyLoadResult:
    return load_ytd_monthly_from_sheet(force_refresh=force_refresh)


def clear_ytd_monthly_cache() -> None:
    global _cache
    _cache = None
