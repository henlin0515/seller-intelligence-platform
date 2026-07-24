"""Business timezone helpers for daily BI refresh."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from seller.intelligence.business_time import business_today
from seller.intelligence.periods import resolve_periods


class BusinessTodayTests(unittest.TestCase):
    def test_manila_date_at_utc_1605_is_next_calendar_day(self):
        # 2026-07-23 16:05 UTC == 2026-07-24 00:05 Asia/Manila
        now = datetime(2026, 7, 23, 16, 5, tzinfo=timezone.utc)
        today = business_today(now)
        self.assertEqual(today.isoformat(), "2026-07-24")
        periods = resolve_periods(today)
        self.assertEqual(periods.mtd.end.isoformat(), "2026-07-23")
        self.assertEqual(periods.mtd.day_count, 23)
        self.assertEqual(periods.m1.end.isoformat(), "2026-06-23")


if __name__ == "__main__":
    unittest.main()
