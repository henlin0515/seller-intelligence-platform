"""Business calendar day for Seller Intelligence periods (Asia/Manila)."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger("seller.intelligence.business_time")

# Philippines does not observe DST — fixed UTC+8 is a safe fallback.
_MANILA_OFFSET = timezone(timedelta(hours=8), name="Asia/Manila")


def business_timezone_name() -> str:
    return (os.getenv("BUSINESS_TIMEZONE") or "Asia/Manila").strip() or "Asia/Manila"


def _tzinfo():
    name = business_timezone_name()
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception as exc:
        logger.warning(
            "ZoneInfo %s unavailable (%s) — using fixed UTC+8",
            name,
            exc,
        )
        return _MANILA_OFFSET


def business_now(now: datetime | None = None) -> datetime:
    """Current datetime in the business timezone (default Asia/Manila)."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(_tzinfo())


def business_today(now: datetime | None = None) -> date:
    """
    Calendar date for MTD / M-1 / daily BI refresh.

    Railway containers often run in UTC. At 00:05 Asia/Manila (16:05 UTC previous
    calendar day), ``date.today()`` in UTC is still yesterday — so daily refresh
    would miss the newly settled day. Always use Manila local date instead.
    """
    return business_now(now).date()
