"""Portfolio-level Business Intelligence aggregates."""

from __future__ import annotations

from typing import Any

from seller.intelligence.business.calculations import mom_percent, sob_pair


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _round_usd(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def _round_pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 1)


def _mapped_sellers(sellers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in sellers if str(s.get("fastmoss_match_status") or "") == "MAPPED"]


def _seller_total_mtd(s: dict[str, Any]) -> float:
    return _num(s.get("shopee_mtd_adgmv_usd")) + _num(s.get("tiktok_mtd_adgmv_usd"))


def _seller_total_m1(s: dict[str, Any]) -> float:
    return _num(s.get("shopee_m1_adgmv_usd")) + _num(s.get("tiktok_m1_adgmv_usd"))


def _segment_seller(total_mtd: float, total_m1: float) -> str | None:
    if total_mtd == 0 and total_m1 == 0:
        return None
    if total_m1 == 0:
        return "growing" if total_mtd > 0 else None
    change_pct = (total_mtd - total_m1) / total_m1 * 100.0
    if change_pct > 5:
        return "growing"
    if change_pct < -5:
        return "declining"
    return "flat"


def build_portfolio_overview(
    sellers: list[dict[str, Any]],
    *,
    total_sellers: int | None = None,
) -> dict[str, Any]:
    """Aggregate portfolio metrics across FastMoss-mapped sellers."""
    all_count = total_sellers if total_sellers is not None else len(sellers)
    mapped = _mapped_sellers(sellers)
    mapped_count = len(mapped)

    shopee_mtd = sum(_num(s.get("shopee_mtd_adgmv_usd")) for s in mapped)
    shopee_m1 = sum(_num(s.get("shopee_m1_adgmv_usd")) for s in mapped)
    tiktok_mtd = sum(_num(s.get("tiktok_mtd_adgmv_usd")) for s in mapped)
    tiktok_m1 = sum(_num(s.get("tiktok_m1_adgmv_usd")) for s in mapped)

    portfolio_total_mtd = shopee_mtd + tiktok_mtd
    portfolio_total_m1 = shopee_m1 + tiktok_m1

    mtd_shopee_sob, mtd_tiktok_sob = sob_pair(shopee_mtd, tiktok_mtd)
    m1_shopee_sob, m1_tiktok_sob = sob_pair(shopee_m1, tiktok_m1)

    growing = flat = declining = 0
    for seller in mapped:
        segment = _segment_seller(_seller_total_mtd(seller), _seller_total_m1(seller))
        if segment == "growing":
            growing += 1
        elif segment == "flat":
            flat += 1
        elif segment == "declining":
            declining += 1

    top_rows: list[dict[str, Any]] = []
    for seller in mapped:
        sh_mtd = _num(seller.get("shopee_mtd_adgmv_usd"))
        tk_mtd = _num(seller.get("tiktok_mtd_adgmv_usd"))
        total_mtd = sh_mtd + tk_mtd
        if total_mtd <= 0:
            continue
        top_rows.append(
            {
                "shop_id": seller.get("shop_id"),
                "shop_name": seller.get("shop_name"),
                "shopee_mtd_adgmv_usd": _round_usd(sh_mtd),
                "tiktok_mtd_adgmv_usd": _round_usd(tk_mtd),
                "total_mtd_adgmv_usd": _round_usd(total_mtd),
                "contribution_percent": None,
            }
        )
    top_rows.sort(key=lambda row: _num(row.get("total_mtd_adgmv_usd")), reverse=True)
    top5 = top_rows[:5]
    for row in top5:
        total = _num(row.get("total_mtd_adgmv_usd"))
        row["contribution_percent"] = (
            _round_pct(total / portfolio_total_mtd * 100.0) if portfolio_total_mtd else None
        )

    threat_rows: list[dict[str, Any]] = []
    for seller in mapped:
        tk_sob = seller.get("mtd_tiktok_sob_percent")
        if tk_sob is None:
            continue
        threat_rows.append(
            {
                "shop_id": seller.get("shop_id"),
                "shop_name": seller.get("shop_name"),
                "tiktok_mtd_sob_percent": _round_pct(_num(tk_sob)),
                "tiktok_mtd_adgmv_usd": seller.get("tiktok_mtd_adgmv_usd"),
                "shopee_mtd_adgmv_usd": seller.get("shopee_mtd_adgmv_usd"),
                "tiktok_mom_percent": seller.get("tiktok_mom_percent"),
            }
        )
    threat_rows.sort(key=lambda row: _num(row.get("tiktok_mtd_sob_percent")), reverse=True)

    mapping_rate = (mapped_count / all_count * 100.0) if all_count else None

    return {
        "total_sellers": all_count,
        "mapped_sellers": mapped_count,
        "shopee_mtd_adgmv_usd": _round_usd(shopee_mtd),
        "shopee_m1_adgmv_usd": _round_usd(shopee_m1),
        "tiktok_mtd_adgmv_usd": _round_usd(tiktok_mtd),
        "tiktok_m1_adgmv_usd": _round_usd(tiktok_m1),
        "portfolio_total_mtd_adgmv_usd": _round_usd(portfolio_total_mtd),
        "portfolio_total_m1_adgmv_usd": _round_usd(portfolio_total_m1),
        "portfolio_sob_mtd_shopee_percent": _round_pct(mtd_shopee_sob),
        "portfolio_sob_mtd_tiktok_percent": _round_pct(mtd_tiktok_sob),
        "portfolio_sob_m1_shopee_percent": _round_pct(m1_shopee_sob),
        "portfolio_sob_m1_tiktok_percent": _round_pct(m1_tiktok_sob),
        "shopee_mom_percent": _round_pct(mom_percent(shopee_mtd, shopee_m1)),
        "tiktok_mom_percent": _round_pct(mom_percent(tiktok_mtd, tiktok_m1)),
        "mapping_rate_percent": _round_pct(mapping_rate),
        "growing_seller_count": growing,
        "flat_seller_count": flat,
        "declining_seller_count": declining,
        "top5_seller_contribution": top5,
        "top_tiktok_threat_sellers": threat_rows[:5],
    }
