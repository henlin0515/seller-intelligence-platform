"""Portfolio-level Historical SOB aggregates."""

from __future__ import annotations

from typing import Any

from seller.intelligence.business.calculations import sob_pair


def _sum(values: list[float | None]) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums)


def _round_gmv(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def _round_sob(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 1)


def build_portfolio_historical_sob(rows: list[dict[str, Any]]) -> dict[str, Any]:
    april_shopee = _sum([r.get("april_shopee_gmv") for r in rows])
    april_tiktok = _sum([r.get("april_tiktok_gmv") for r in rows])
    may_shopee = _sum([r.get("may_shopee_gmv") for r in rows])
    may_tiktok = _sum([r.get("may_tiktok_gmv") for r in rows])

    april_total = (
        (april_shopee + april_tiktok)
        if april_shopee is not None and april_tiktok is not None
        else None
    )
    may_total = (
        (may_shopee + may_tiktok) if may_shopee is not None and may_tiktok is not None else None
    )

    april_shopee_sob, april_tiktok_sob = (
        sob_pair(float(april_shopee), float(april_tiktok))
        if april_shopee is not None and april_tiktok is not None
        else (None, None)
    )
    may_shopee_sob, may_tiktok_sob = (
        sob_pair(float(may_shopee), float(may_tiktok))
        if may_shopee is not None and may_tiktok is not None
        else (None, None)
    )

    portfolio_sob_change_pp = None
    if april_tiktok_sob is not None and may_tiktok_sob is not None:
        portfolio_sob_change_pp = _round_sob(float(may_tiktok_sob) - float(april_tiktok_sob))

    return {
        "april_shopee_gmv": _round_gmv(april_shopee),
        "april_tiktok_gmv": _round_gmv(april_tiktok),
        "april_total_gmv": _round_gmv(april_total),
        "may_shopee_gmv": _round_gmv(may_shopee),
        "may_tiktok_gmv": _round_gmv(may_tiktok),
        "may_total_gmv": _round_gmv(may_total),
        "april_shopee_sob_percent": _round_sob(april_shopee_sob),
        "april_tiktok_sob_percent": _round_sob(april_tiktok_sob),
        "april_portfolio_sob_percent": _round_sob(april_tiktok_sob),
        "may_shopee_sob_percent": _round_sob(may_shopee_sob),
        "may_tiktok_sob_percent": _round_sob(may_tiktok_sob),
        "may_portfolio_sob_percent": _round_sob(may_tiktok_sob),
        "portfolio_sob_change_pp": portfolio_sob_change_pp,
    }


def build_top_sob_movers(rows: list[dict[str, Any]], *, limit: int = 15) -> list[dict[str, Any]]:
    movers = [r for r in rows if r.get("sob_change_pp") is not None]
    movers.sort(key=lambda r: abs(float(r["sob_change_pp"])), reverse=True)
    return movers[:limit]


def build_tiktok_threat_sellers(rows: list[dict[str, Any]], *, limit: int = 15) -> list[dict[str, Any]]:
    threats = [r for r in rows if r.get("may_tiktok_sob_percent") is not None]
    threats.sort(key=lambda r: float(r["may_tiktok_sob_percent"]), reverse=True)
    return threats[:limit]
