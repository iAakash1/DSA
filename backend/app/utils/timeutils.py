"""Timezone handling.

Everything is stored in UTC. Everything *user-facing* — streaks, the heatmap,
daily goals, missions — is bucketed by the calendar date in the user's own
timezone. Mixing those two is the classic source of off-by-one streak bugs, so
conversion happens in exactly one place: here.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

_UTC = timezone.utc


def get_zone(tz_name: str | None) -> ZoneInfo:
    """Resolve a timezone name, falling back to the configured default.

    Never raises: a bad timezone in the database must not break the dashboard.
    """
    for candidate in (tz_name, settings.default_timezone, "UTC"):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            continue
    return ZoneInfo("UTC")


def utcnow() -> datetime:
    return datetime.now(_UTC)


def to_utc(dt: datetime) -> datetime:
    """Coerce any datetime to tz-aware UTC (naive is assumed to be UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_UTC)
    return dt.astimezone(_UTC)


def local_date(dt: datetime, tz_name: str | None) -> date:
    """The calendar date `dt` falls on, as the user experiences it."""
    return to_utc(dt).astimezone(get_zone(tz_name)).date()


def today_in(tz_name: str | None) -> date:
    return utcnow().astimezone(get_zone(tz_name)).date()


def day_bounds_utc(day: date, tz_name: str | None) -> tuple[datetime, datetime]:
    """UTC half-open interval [start, end) covering one local calendar day.

    DST-safe: the day is anchored in local time and then converted, so a 23- or
    25-hour day produces the correct span.
    """
    zone = get_zone(tz_name)
    start_local = datetime.combine(day, time.min, tzinfo=zone)
    end_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start_local.astimezone(_UTC), end_local.astimezone(_UTC)


def range_bounds_utc(
    start_day: date, end_day: date, tz_name: str | None
) -> tuple[datetime, datetime]:
    """UTC interval covering [start_day, end_day] inclusive of both local days."""
    start, _ = day_bounds_utc(start_day, tz_name)
    _, end = day_bounds_utc(end_day, tz_name)
    return start, end


def week_start(day: date, week_starts_monday: bool = True) -> date:
    """Monday-based week start (ISO convention)."""
    offset = day.weekday() if week_starts_monday else (day.weekday() + 1) % 7
    return day - timedelta(days=offset)


def days_between(earlier: date, later: date) -> int:
    return (later - earlier).days


def days_since(dt: datetime | None, tz_name: str | None) -> int | None:
    """Whole local days since `dt`. None when there is no data."""
    if dt is None:
        return None
    return days_between(local_date(dt, tz_name), today_in(tz_name))


def iter_dates(start: date, end: date):
    """Inclusive date iterator."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)
