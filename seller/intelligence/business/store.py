"""Business Intelligence V1 — persisted FastMoss TikTok collection."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_BI_DATA_PATH = Path(
    os.getenv("BUSINESS_INTELLIGENCE_DATA_PATH", "business_intelligence_data.json")
)


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
    target = bi_data_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return target.resolve()


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
