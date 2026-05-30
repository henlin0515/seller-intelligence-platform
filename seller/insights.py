"""Strengths / Opportunities / Risks from visible mapped metrics only."""

from __future__ import annotations

from typing import Any


def _g(m: dict[str, Any]) -> float | None:
    g = m.get("growthPct", m.get("growth"))
    if g is None:
        return None
    try:
        return float(g)
    except (TypeError, ValueError):
        return None


def _find(sections: list[dict[str, Any]], section_key: str, metric_key: str) -> dict[str, Any] | None:
    for s in sections:
        if s.get("key") != section_key:
            continue
        for m in s.get("metrics", []):
            if m.get("key") == metric_key:
                return m
    return None


def build_insights(
    sections: list[dict[str, Any]],
    health: dict[str, Any],
) -> dict[str, list[str]]:
    strengths: list[str] = []
    opportunities: list[str] = []
    risks: list[str] = []

    score = health.get("score")
    if isinstance(score, (int, float)) and score >= 75:
        strengths.append(f"Overall health score is {score} ({health.get('label', 'Healthy')}).")
    elif isinstance(score, (int, float)) and score < 50:
        risks.append(f"Overall health score is {score} ({health.get('label', 'At Risk')}) — prioritize recovery actions.")

    for key, label in (
        ("adgmv", "ADGMV"),
        ("ado", "ADO"),
        ("uv", "UV"),
    ):
        m = _find(sections, "commercial", key)
        if not m:
            continue
        g = _g(m)
        mtd = m.get("mtd_display", "")
        if g is not None and g >= 10:
            strengths.append(f"{label} is growing {g:+.1f}% MTD ({mtd}).")
        elif g is not None and g <= -10:
            risks.append(f"{label} declined {g:+.1f}% vs M-1 ({mtd} MTD).")
        elif g is not None and -10 < g < 5:
            opportunities.append(f"{label} is flat or soft ({g:+.1f}%); test campaigns to re-accelerate.")

    roas = _find(sections, "paid_ads", "roas")
    take = _find(sections, "paid_ads", "take_rate")
    if roas and roas.get("mtdValue") is not None:
        rv = float(roas["mtdValue"])
        if rv >= 8:
            strengths.append(f"Paid Ads ROAS is strong at {roas.get('mtd_display', rv)}x.")
        elif rv < 5 and rv > 0:
            risks.append(f"Paid Ads ROAS is below target ({roas.get('mtd_display', rv)}x).")
    if take and roas and take.get("mtdValue") is not None and roas.get("mtdValue") is not None:
        if float(roas["mtdValue"]) >= 8 and float(take["mtdValue"]) < 2:
            opportunities.append(
                f"ROAS is efficient ({roas.get('mtd_display')}) but take rate is low ({take.get('mtd_display')}) — room to scale spend."
            )

    mdv = _find(sections, "mdv", "adg_pct")
    if mdv and _g(mdv) is not None and _g(mdv) >= 5:
        strengths.append(f"MDV contributes {mdv.get('mtd_display', '')} of ADGMV and is trending up.")

    video = _find(sections, "video", "adg_pct")
    if video and _g(video) is not None and _g(video) >= 5:
        strengths.append(f"Video Adg% is expanding ({video.get('growth_display', '')}).")

    if not strengths:
        strengths.append("Core commercial metrics are loaded — monitor week-over-week momentum.")
    if not opportunities:
        opportunities.append("Review Ads efficiency and MDV/Video contribution for upside.")
    if not risks:
        risks.append("No critical declines detected in visible metrics this period.")

    return {
        "strengths": strengths[:5],
        "opportunities": opportunities[:5],
        "risks": risks[:5],
    }
