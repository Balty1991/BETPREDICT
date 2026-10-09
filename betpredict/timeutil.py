"""Ziua „aplicației” este ziua din România (Europe/Bucharest); API-ul lucrează în UTC."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

try:
    from zoneinfo import ZoneInfo

    RO_TZ = ZoneInfo("Europe/Bucharest")
except Exception:  # pragma: no cover - fără tzdata
    RO_TZ = timezone(timedelta(hours=3))


def ro_today(now: Optional[datetime] = None) -> date:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(RO_TZ).date()


def parse_utc(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def canon_utc(ts: object) -> Optional[str]:
    """Format canonic pentru stocare/comparare lexicografică: ``YYYY-MM-DDTHH:MM:SSZ``."""
    dt = parse_utc(str(ts)) if ts else None
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def ro_date_of(ts: str) -> Optional[date]:
    dt = parse_utc(ts)
    return dt.astimezone(RO_TZ).date() if dt else None


def ro_day_bounds_utc(day: date) -> tuple[str, str]:
    """[start, end) în UTC pentru ziua din România."""
    start = datetime(day.year, day.month, day.day, tzinfo=RO_TZ).astimezone(timezone.utc)
    end = (datetime(day.year, day.month, day.day, tzinfo=RO_TZ) + timedelta(days=1)).astimezone(timezone.utc)
    return canon_utc(start.isoformat()), canon_utc(end.isoformat())
