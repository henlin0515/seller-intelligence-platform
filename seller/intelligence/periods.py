"""Seller Intelligence V1 — MTD / M-1 period helpers (no live date fetching)."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class PeriodRange:
    start: date
    end: date

    @property
    def day_count(self) -> int:
        """Inclusive calendar days in the range."""
        return (self.end - self.start).days + 1

    def as_dict(self) -> dict[str, str]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
        }


@dataclass(frozen=True)
class IntelligencePeriods:
    """Latest settled date excludes today."""

    reference_today: date
    latest_settled_date: date
    mtd: PeriodRange
    m1: PeriodRange

    def as_dict(self) -> dict[str, object]:
        return {
            "reference_today": self.reference_today.isoformat(),
            "latest_settled_date": self.latest_settled_date.isoformat(),
            "mtd": self.mtd.as_dict(),
            "m1": self.m1.as_dict(),
        }


def latest_settled_date(today: date) -> date:
    """Use latest settled date only — do not include today."""
    return today - timedelta(days=1)


def _previous_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def resolve_periods(today: date) -> IntelligencePeriods:
    """
    Period logic (examples from spec):

    - today 2026-06-07 → MTD 2026-06-01..2026-06-06, M-1 2026-05-01..2026-05-06
    - today 2026-06-01 → MTD 2026-05-01..2026-05-31, M-1 2026-04-01..2026-04-30
    - today 2026-07-23 → MTD 2026-07-01..2026-07-22, M-1 2026-06-01..2026-06-22
    """
    settled = latest_settled_date(today)

    if today.day == 1:
        mtd_start = date(settled.year, settled.month, 1)
        mtd_end = settled
        py, pm = _previous_month(settled.year, settled.month)
        m1_start = date(py, pm, 1)
        m1_end = date(py, pm, calendar.monthrange(py, pm)[1])
    else:
        mtd_start = date(today.year, today.month, 1)
        mtd_end = settled
        py, pm = _previous_month(today.year, today.month)
        last_day_prev = calendar.monthrange(py, pm)[1]
        m1_start = date(py, pm, 1)
        m1_end = date(py, pm, min(settled.day, last_day_prev))

    return IntelligencePeriods(
        reference_today=today,
        latest_settled_date=settled,
        mtd=PeriodRange(mtd_start, mtd_end),
        m1=PeriodRange(m1_start, m1_end),
    )


def periods_match_payload(
    saved_periods: dict[str, object] | None,
    current: IntelligencePeriods,
) -> bool:
    """True when saved FastMoss collection periods match current UI MTD / M-1 tags."""
    if not isinstance(saved_periods, dict):
        return False
    mtd = saved_periods.get("mtd") or {}
    m1 = saved_periods.get("m1") or {}
    if not isinstance(mtd, dict) or not isinstance(m1, dict):
        return False
    return (
        str(mtd.get("start") or "") == current.mtd.start.isoformat()
        and str(mtd.get("end") or "") == current.mtd.end.isoformat()
        and str(m1.get("start") or "") == current.m1.start.isoformat()
        and str(m1.get("end") or "") == current.m1.end.isoformat()
    )


def collection_row_matches_periods(
    row: dict[str, object] | None,
    current: IntelligencePeriods,
) -> bool:
    """True when a collected seller row was fetched for the current UI periods."""
    if not isinstance(row, dict):
        return False
    mtd_start = str(row.get("mtd_start") or "").strip()
    mtd_end = str(row.get("mtd_end") or "").strip()
    m1_start = str(row.get("m1_start") or "").strip()
    m1_end = str(row.get("m1_end") or "").strip()
    if mtd_start and mtd_end and m1_start and m1_end:
        return (
            mtd_start == current.mtd.start.isoformat()
            and mtd_end == current.mtd.end.isoformat()
            and m1_start == current.m1.start.isoformat()
            and m1_end == current.m1.end.isoformat()
        )
    # Legacy rows without per-row dates: caller must check file-level periods.
    return True
