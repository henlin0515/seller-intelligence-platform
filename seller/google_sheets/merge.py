"""
Merge mirror spreadsheet tabs into one seller dataset keyed by Shop ID.
Preserves all columns; suffixes duplicates with tab slug.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("seller.google_sheets.merge")

SHOP_ID_HEADER_CANDIDATES = (
    "shop id",
    "shop_id",
    "shopid",
    "seller shop id",
    "seller_shop_id",
    "shop code",
    "shop_code",
)

SHOP_NAME_HEADER_CANDIDATES = (
    "shop name",
    "shop_name",
    "seller name",
    "seller shop name",
    "store name",
)

TIER_HEADER_CANDIDATES = ("tier", "shop tier", "seller tier")
CATEGORY_HEADER_CANDIDATES = ("category", "l1 category", "shop category", "vertical")

SKIP_TAB_NAME_PATTERNS = re.compile(
    r"(readme|instruction|template|config|changelog|notes|sheet\d+$)",
    re.I,
)

MERGE_STRATEGY_LABEL = (
    "left_join_on_shop_id: primary tab defines seller universe; "
    "other tabs merged by normalized Shop ID; duplicate column names "
    "suffixed with __{tab_slug}; all original headers preserved"
)


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", (h or "").strip()).lower()


def _sanitize_column_key(header: str) -> str:
    key = re.sub(r"\s+", "_", (header or "").strip())
    key = re.sub(r"[^\w\-.]+", "_", key, flags=re.UNICODE)
    key = re.sub(r"_+", "_", key).strip("_")
    return key or "column"


def tab_slug(title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_").lower()
    return slug[:48] or "tab"


def detect_shop_id_header(headers: list[str]) -> str | None:
    normalized = {_norm_header(h): h for h in headers if h}
    for candidate in SHOP_ID_HEADER_CANDIDATES:
        if candidate in normalized:
            return normalized[candidate]
    for h in headers:
        nh = _norm_header(h)
        if nh.endswith("shop id") or nh == "id" and "shop" in nh:
            return h
    return None


def _pick_meta(headers: list[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {_norm_header(h): h for h in headers if h}
    for c in candidates:
        if c in normalized:
            return normalized[c]
    return None


def normalize_shop_id(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("#n/a", "n/a", "-", ""):
        return None
    return s


def grid_to_records(grid: list[list[Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    if not grid:
        return [], []
    header_row_idx = 0
    for i, row in enumerate(grid[:10]):
        if any(str(c).strip() for c in row):
            header_row_idx = i
            break
    headers = [str(c).strip() for c in grid[header_row_idx]]
    records: list[dict[str, Any]] = []
    for row in grid[header_row_idx + 1 :]:
        if not any(str(c).strip() for c in row):
            continue
        padded = list(row) + [""] * max(0, len(headers) - len(row))
        rec = {headers[j]: padded[j] for j in range(len(headers)) if headers[j]}
        records.append(rec)
    return headers, records


def should_skip_tab(title: str) -> bool:
    return bool(SKIP_TAB_NAME_PATTERNS.search(title))


def choose_primary_tab(titles: list[str], hint: str) -> str:
    from seller.google_sheets.ai_data_layout import resolve_ai_data_tab_title

    resolved = resolve_ai_data_tab_title(titles)
    if resolved:
        return resolved
    if hint in titles:
        return hint
    for t in titles:
        if "raw" in t.lower() and "shop level" in t.lower():
            return t
    for t in titles:
        if "fashion" in t.lower() and "raw" in t.lower():
            return t
    return titles[0] if titles else hint


def apply_resolver_aliases(raw: dict[str, Any]) -> dict[str, Any]:
    """Duplicate values under uppercase underscore keys for metric_resolver."""
    out = dict(raw)
    for key, value in list(raw.items()):
        if key.startswith("_"):
            continue
        alias = re.sub(r"\s+", "_", key.strip()).upper()
        alias = re.sub(r"_+", "_", alias)
        if alias and alias not in out:
            out[alias] = value
        # Common MTD / M-1 variants
        low = key.lower().replace(" ", "_")
        if "m-1" in low or "m_1" in low or low.endswith("_m1"):
            alt = re.sub(r"m[-_]?1", "M1", alias, flags=re.I)
            if alt not in out:
                out[alt] = value
        if "mtd" in low:
            alt = alias.replace("M-1", "MTD").replace("M_1", "MTD")
            if "MTD" not in alias and alias + "_MTD" not in out:
                pass
    return out


def merge_tabs(
    tab_grids: dict[str, list[list[Any]]],
    *,
    primary_tab_hint: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """
    Returns (sellers_by_id, load_summary).
    Each seller: { shop_id, shop_name, tier, category, raw, _source_tabs }.
    """
    from seller.google_sheets.ai_data_layout import build_sellers_from_ai_data, resolve_ai_data_tab_title

    ai_tab = resolve_ai_data_tab_title(list(tab_grids.keys()))
    if ai_tab and tab_grids.get(ai_tab):
        sellers, summary = build_sellers_from_ai_data(tab_grids[ai_tab], source_tab=ai_tab)
        summary["tabs_discovered"] = list(tab_grids.keys())
        other = [t for t in tab_grids if t != ai_tab and not should_skip_tab(t)]
        if other:
            logger.info(
                "Seller Performance uses %r only; other tabs ignored: %s",
                ai_tab,
                other,
            )
        return sellers, summary

    titles = [t for t in tab_grids if not should_skip_tab(t)]
    if not titles:
        raise ValueError("No usable tabs found in mirror spreadsheet")

    primary_title = choose_primary_tab(titles, primary_tab_hint)
    shop_id_field_global: str | None = None
    tab_structures: list[dict[str, Any]] = []
    parsed_tabs: dict[str, tuple[list[str], list[dict[str, Any]], str | None]] = {}

    total_grid_rows = 0
    for title, grid in tab_grids.items():
        if should_skip_tab(title):
            continue
        total_grid_rows += len(grid)
        headers, records = grid_to_records(grid)
        shop_col = detect_shop_id_header(headers)
        parsed_tabs[title] = (headers, records, shop_col)
        tab_structures.append(
            {
                "title": title,
                "grid_rows": len(grid),
                "header_count": len(headers),
                "data_rows": len(records),
                "shop_id_header": shop_col,
                "headers_sample": headers[:12],
            }
        )
        if title == primary_title and shop_col:
            shop_id_field_global = shop_col

    if primary_title not in parsed_tabs:
        raise ValueError(f"Primary tab not found: {primary_title}")

    p_headers, p_records, p_shop_col = parsed_tabs[primary_title]
    if not p_shop_col:
        raise ValueError(f"Shop ID column not found on primary tab: {primary_title}")

    shop_id_field_global = shop_id_field_global or p_shop_col
    sellers: dict[str, dict[str, Any]] = {}

    def merge_record_into(shop_id: str, record: dict[str, Any], tab_title: str, shop_col: str) -> None:
        slug = tab_slug(tab_title)
        entry = sellers.get(shop_id)
        if not entry:
            entry = {
                "shop_id": shop_id,
                "shop_name": "",
                "tier": "",
                "category": "",
                "raw": {},
                "_source_tabs": [],
            }
            sellers[shop_id] = entry
        if tab_title not in entry["_source_tabs"]:
            entry["_source_tabs"].append(tab_title)

        name_col = _pick_meta(list(record.keys()), SHOP_NAME_HEADER_CANDIDATES)
        tier_col = _pick_meta(list(record.keys()), TIER_HEADER_CANDIDATES)
        cat_col = _pick_meta(list(record.keys()), CATEGORY_HEADER_CANDIDATES)
        if tab_title == primary_title or not entry["shop_name"]:
            if name_col and record.get(name_col):
                entry["shop_name"] = str(record[name_col]).strip()
            if tier_col and record.get(tier_col):
                entry["tier"] = str(record[tier_col]).strip()
            if cat_col and record.get(cat_col):
                entry["category"] = str(record[cat_col]).strip()

        for header, value in record.items():
            if header == shop_col:
                continue
            key = _sanitize_column_key(header)
            if key in entry["raw"] and entry["raw"][key] != value:
                key = f"{key}__{slug}"
            entry["raw"][key] = value
            entry["raw"][f"_tab.{slug}.{key}"] = tab_title

    for rec in p_records:
        sid = normalize_shop_id(rec.get(p_shop_col))
        if sid:
            merge_record_into(sid, rec, primary_title, p_shop_col)

    for title, (headers, records, shop_col) in parsed_tabs.items():
        if title == primary_title or not shop_col:
            continue
        for rec in records:
            sid = normalize_shop_id(rec.get(shop_col))
            if sid and sid in sellers:
                merge_record_into(sid, rec, title, shop_col)
            elif sid and title != primary_title:
                # Secondary-only shops: include if not in primary
                merge_record_into(sid, rec, title, shop_col)

    for sid, entry in sellers.items():
        entry["raw"]["_shop_id"] = sid
        entry["raw"]["_source_tabs"] = list(entry["_source_tabs"])
        entry["raw"] = apply_resolver_aliases(entry["raw"])
        if not entry["shop_name"]:
            entry["shop_name"] = sid

    column_keys: set[str] = set()
    for entry in sellers.values():
        column_keys.update(entry["raw"].keys())

    summary = {
        "merge_strategy": MERGE_STRATEGY_LABEL,
        "primary_tab": primary_title,
        "shop_id_field": shop_id_field_global,
        "tabs_discovered": list(tab_grids.keys()),
        "tabs_merged": [t for t in parsed_tabs if not should_skip_tab(t)],
        "tabs_skipped": [t for t in tab_grids if should_skip_tab(t)],
        "tab_structures": tab_structures,
        "seller_count": len(sellers),
        "total_grid_rows_read": total_grid_rows,
        "total_columns_merged": len(column_keys),
        "spreadsheet_title": None,
    }
    logger.info(
        "Merged %s sellers from %s tabs (primary=%s)",
        len(sellers),
        len(parsed_tabs),
        primary_title,
    )
    return sellers, summary
