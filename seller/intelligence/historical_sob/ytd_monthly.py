"""YTD monthly Shopee ADGMV from Google Sheet tab ``ytd monthly data``."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from seller.google_sheets.client import get_sheets_client
from seller.google_sheets.config import is_configured
from seller.google_sheets.exceptions import GoogleSheetsNotConfiguredError

logger = logging.getLogger("seller.intelligence.historical_sob.ytd_monthly")

DEFAULT_YTD_MONTHLY_TAB = "ytd monthly data"

APRIL_DAY_COUNT = 30
MAY_DAY_COUNT = 31

_HEADER_SHOP_NAME = re.compile(r"^shop[_\s-]*name$", re.I)
_HEADER_SHOP_ID = re.compile(r"^shop[_\s-]*id$", re.I)
_HEADER_YTD_APR = re.compile(r"^ytd_ap(?:r)?[_\s-]*adgmv$", re.I)
_HEADER_YTD_MAY = re.compile(r"^ytd_may[_\s-]*adgmv$", re.I)


def normalize_shop_name(name: str) -> str:
    """Trim + case-insensitive key for matching shpoee link shop names."""
    return (name or "").strip().casefold()


def normalize_tab_name(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip()).lower()


def resolve_ytd_monthly_tab_title(titles: list[str], hint: str | None = None) -> str | None:
    """Resolve mirror tab for Historical SOB YTD data (case/spacing tolerant)."""
    if not titles:
        return None
    preferred = (hint or ytd_monthly_tab_name()).strip()
    if preferred in titles:
        return preferred

    by_norm = {normalize_tab_name(title): title for title in titles}
    hit = by_norm.get(normalize_tab_name(preferred))
    if hit:
        return hit

    for norm, original in by_norm.items():
        compact = norm.replace(" ", "").replace("_", "")
        if compact == "ytdmonthlydata":
            return original
        if "ytd" in norm and "month" in norm:
            return original
    return None


def _ytd_tab_name_candidates(titles: list[str], hint: str) -> list[str]:
    """Prefer tabs whose names look like YTD monthly before scanning headers."""
    resolved = resolve_ytd_monthly_tab_title(titles, hint)
    if resolved:
        return [resolved]

    scored: list[tuple[int, str]] = []
    hint_norm = normalize_tab_name(hint)
    for title in titles:
        norm = normalize_tab_name(title)
        compact = norm.replace(" ", "").replace("_", "")
        score = 0
        if norm == hint_norm:
            score += 100
        if "ytd" in norm:
            score += 40
        if "month" in norm:
            score += 30
        if "data" in norm:
            score += 10
        if compact == "ytdmonthlydata":
            score += 80
        if score:
            scored.append((score, title))
    scored.sort(key=lambda item: (-item[0], item[1].lower()))
    return [title for _, title in scored]


def _header_row_has_ytd_columns(header_row: list[Any]) -> bool:
    has_shop_name = False
    has_apr = False
    has_may = False
    for cell in header_row:
        label = _cell([cell], 0).lower()
        if _HEADER_SHOP_NAME.match(label):
            has_shop_name = True
        elif _HEADER_YTD_APR.match(label):
            has_apr = True
        elif _HEADER_YTD_MAY.match(label):
            has_may = True
    return has_shop_name and (has_apr or has_may)


def discover_ytd_monthly_tab(
    client: Any,
    titles: list[str],
    *,
    hint: str | None = None,
) -> tuple[str | None, list[list[Any]] | None]:
    """Resolve tab by name, then scan likely tabs for YTD header columns."""
    preferred = (hint or ytd_monthly_tab_name()).strip()
    candidates = _ytd_tab_name_candidates(titles, preferred)
    for title in candidates:
        rows = client.fetch_worksheet_values(title)
        if rows and _header_row_has_ytd_columns(rows[0]):
            return title, rows
    return None, None


@dataclass(frozen=True)
class YtdMonthlyRecord:
    shop_id: str
    shop_name: str
    ytd_apr_adgmv: float | None
    ytd_may_adgmv: float | None

    @property
    def april_shopee_gmv(self) -> float | None:
        if self.ytd_apr_adgmv is None:
            return None
        return self.ytd_apr_adgmv * APRIL_DAY_COUNT

    @property
    def may_shopee_gmv(self) -> float | None:
        if self.ytd_may_adgmv is None:
            return None
        return self.ytd_may_adgmv * MAY_DAY_COUNT


@dataclass
class YtdMonthlyImportStats:
    total_rows_read: int = 0
    total_loaded: int = 0
    duplicate_shop_names: list[str] = field(default_factory=list)
    duplicate_shop_ids: list[str] = field(default_factory=list)
    skipped_rows: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_rows_read": self.total_rows_read,
            "total_loaded": self.total_loaded,
            "duplicate_shop_name_count": len(self.duplicate_shop_names),
            "duplicate_shop_names": self.duplicate_shop_names,
            "duplicate_shop_id_count": len(self.duplicate_shop_ids),
            "duplicate_shop_ids": self.duplicate_shop_ids,
            "skipped_row_count": len(self.skipped_rows),
            "skipped_rows": self.skipped_rows,
        }


@dataclass
class YtdMonthlyLoadResult:
    by_shop_name: dict[str, YtdMonthlyRecord]
    by_shop_id: dict[str, YtdMonthlyRecord]
    stats: YtdMonthlyImportStats
    tab: str
    data_source: str
    load_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "tab": self.tab,
            "data_source": self.data_source,
            "load_error": self.load_error,
            "import": self.stats.as_dict(),
            "loaded_count": len(self.by_shop_name),
        }


_cache: YtdMonthlyLoadResult | None = None


def ytd_monthly_tab_name() -> str:
    return (os.getenv("GOOGLE_SHEET_YTD_MONTHLY_TAB") or DEFAULT_YTD_MONTHLY_TAB).strip()


def _cell(row: list[Any], index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _parse_optional_float(value: str) -> float | None:
    text = (value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _header_indexes(header_row: list[Any]) -> dict[str, int]:
    indexes: dict[str, int] = {}
    for index, cell in enumerate(header_row):
        label = _cell([cell], 0).lower()
        if _HEADER_SHOP_NAME.match(label):
            indexes["shop_name"] = index
        elif _HEADER_SHOP_ID.match(label):
            indexes["shop_id"] = index
        elif _HEADER_YTD_APR.match(label):
            indexes["ytd_apr_adgmv"] = index
        elif _HEADER_YTD_MAY.match(label):
            indexes["ytd_may_adgmv"] = index

    indexes.setdefault("shop_name", 0)
    indexes.setdefault("shop_id", 1)
    indexes.setdefault("ytd_apr_adgmv", 2)
    indexes.setdefault("ytd_may_adgmv", 3)
    return indexes


def lookup_ytd_record(
    ytd: YtdMonthlyLoadResult,
    *,
    shop_name: str,
    shop_id: str = "",
) -> YtdMonthlyRecord | None:
    """Match ytd monthly row to seller master by shop_id, with shop_name fallback."""
    sid = str(shop_id or "").strip()
    if sid:
        record = ytd.by_shop_id.get(sid)
        if record is not None:
            return record
    name_key = normalize_shop_name(shop_name)
    if name_key:
        return ytd.by_shop_name.get(name_key)
    return None


def parse_ytd_monthly_rows(
    rows: list[list[Any]],
    *,
    tab: str = DEFAULT_YTD_MONTHLY_TAB,
) -> YtdMonthlyLoadResult:
    """Parse grid: shop_name, shop_id, ytd_apr_adgmv, ytd_may_adgmv (columns A–D)."""
    stats = YtdMonthlyImportStats()
    by_shop_name: dict[str, YtdMonthlyRecord] = {}
    by_shop_id: dict[str, YtdMonthlyRecord] = {}

    if not rows:
        return YtdMonthlyLoadResult(by_shop_name, by_shop_id, stats, tab=tab, data_source="google_sheet")

    indexes = _header_indexes(rows[0])
    for row_index, row in enumerate(rows[1:], start=2):
        stats.total_rows_read += 1
        shop_name = _cell(row, indexes.get("shop_name", 0))
        shop_id = _cell(row, indexes.get("shop_id", 1))
        if not shop_name and not shop_id:
            stats.skipped_rows.append({"row": row_index, "reason": "missing_shop_id_and_shop_name"})
            continue

        name_key = normalize_shop_name(shop_name) if shop_name else ""
        if name_key and name_key in by_shop_name:
            if shop_name not in stats.duplicate_shop_names:
                stats.duplicate_shop_names.append(shop_name)
            stats.skipped_rows.append(
                {"row": row_index, "reason": "duplicate_shop_name", "shop_name": shop_name}
            )
            continue

        if shop_id and shop_id in by_shop_id:
            if shop_id not in stats.duplicate_shop_ids:
                stats.duplicate_shop_ids.append(shop_id)
            stats.skipped_rows.append(
                {"row": row_index, "reason": "duplicate_shop_id", "shop_id": shop_id}
            )
            continue

        record = YtdMonthlyRecord(
            shop_id=shop_id,
            shop_name=shop_name,
            ytd_apr_adgmv=_parse_optional_float(_cell(row, indexes.get("ytd_apr_adgmv", 2))),
            ytd_may_adgmv=_parse_optional_float(_cell(row, indexes.get("ytd_may_adgmv", 3))),
        )
        if name_key:
            by_shop_name[name_key] = record
        if shop_id:
            by_shop_id[shop_id] = record

    stats.total_loaded = len({id(r) for r in set(by_shop_id.values()) | set(by_shop_name.values())})
    return YtdMonthlyLoadResult(
        by_shop_name=by_shop_name,
        by_shop_id=by_shop_id,
        stats=stats,
        tab=tab,
        data_source="google_sheet",
    )


def _empty_result(*, tab: str, load_error: str) -> YtdMonthlyLoadResult:
    return YtdMonthlyLoadResult(
        by_shop_name={},
        by_shop_id={},
        stats=YtdMonthlyImportStats(),
        tab=tab,
        data_source="unavailable",
        load_error=load_error,
    )


def load_ytd_monthly_from_sheet(*, force_refresh: bool = False) -> YtdMonthlyLoadResult:
    global _cache
    if _cache is not None and not force_refresh:
        return _cache

    tab = ytd_monthly_tab_name()
    if not is_configured():
        result = _empty_result(
            tab=tab,
            load_error="Google Sheets is not configured for YTD monthly import.",
        )
        _cache = result
        return result

    try:
        client = get_sheets_client()
        titles = client.list_worksheet_titles()
        resolved_tab = resolve_ytd_monthly_tab_title(titles, tab)
        rows: list[list[Any]] | None = None
        if resolved_tab:
            rows = client.fetch_worksheet_values(resolved_tab)
            tab = resolved_tab
        else:
            discovered_tab, discovered_rows = discover_ytd_monthly_tab(client, titles, hint=tab)
            if discovered_tab and discovered_rows is not None:
                tab = discovered_tab
                rows = discovered_rows
            else:
                similar = [
                    title
                    for title in titles
                    if "ytd" in normalize_tab_name(title) or "month" in normalize_tab_name(title)
                ]
                sample = similar[:8] or titles[:8]
                message = (
                    f"YTD monthly tab not found (expected {tab!r}). "
                    f"Similar tabs: {sample}"
                )
                logger.warning(message)
                result = _empty_result(tab=tab, load_error=message)
                _cache = result
                return result

        result = parse_ytd_monthly_rows(rows or [], tab=tab)
    except GoogleSheetsNotConfiguredError as exc:
        logger.warning("YTD monthly load skipped: %s", exc)
        result = _empty_result(tab=tab, load_error=str(exc))
    except Exception as exc:
        logger.exception("YTD monthly load failed for tab %r", tab)
        result = _empty_result(tab=tab, load_error=f"YTD monthly load failed: {exc}")
    else:
        logger.info(
            "YTD monthly loaded from tab %r: %s shops by shop_name (%s rows read)",
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
