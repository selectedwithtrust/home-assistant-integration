"""Pure opening-hours logic. No Home Assistant imports, so it is trivially testable.

Semantics follow the API contract (docs/opening-info-api.md in the SWT repo):
* times are wall-clock in the business timezone,
* ``close < open`` means the business closes the following day,
* ``open == close`` on an open day means open for 24 hours,
* only ``isClosed`` means closed; a missing day is treated as closed,
* a break is a normal same-day interval removed from the opening interval,
* a holiday override replaces the regular hours for that date only
  (``closed`` / ``custom``; ``regular`` or none = weekly hours).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True, slots=True)
class Interval:
    """A half-open ``[start, end)`` span during which the business is open."""

    start: datetime
    end: datetime


def parse_time(value: str | None) -> time | None:
    """Parse ``HH:MM`` (or ``HH:MM:SS``) into a time, or None."""
    if not value:
        return None
    try:
        parts = [int(p) for p in value.split(":")][:3]
        parts += [0] * (3 - len(parts))
        return time(parts[0], parts[1], parts[2])
    except (ValueError, TypeError):
        return None


def get_zone(name: str | None) -> ZoneInfo:
    """Resolve an IANA zone, falling back to the platform default of the API."""
    try:
        return ZoneInfo(name or "Europe/Amsterdam")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Amsterdam")


def _day_intervals(
    day: date,
    zone: ZoneInfo,
    open_t: time | None,
    close_t: time | None,
    break_start: time | None,
    break_end: time | None,
) -> list[Interval]:
    if open_t is None or close_t is None:
        return []
    start = datetime.combine(day, open_t, tzinfo=zone)
    if close_t == open_t:
        # Wall-clock 24h: use the calendar, not 24 elapsed hours, across DST.
        end = datetime.combine(day + timedelta(days=1), open_t, tzinfo=zone)
    elif close_t < open_t:
        end = datetime.combine(day + timedelta(days=1), close_t, tzinfo=zone)
    else:
        end = datetime.combine(day, close_t, tzinfo=zone)

    if break_start and break_end and break_start < break_end:
        b_start = datetime.combine(day, break_start, tzinfo=zone)
        b_end = datetime.combine(day, break_end, tzinfo=zone)
        # Only applies when the break sits inside the opening span.
        if start < b_start and b_end < end:
            return [Interval(start, b_start), Interval(b_end, end)]
    return [Interval(start, end)]


def build_intervals(
    data: dict[str, Any], first_day: date, days: int
) -> list[Interval]:
    """Expand weekly hours + holiday overrides into merged absolute intervals."""
    zone, weekly, holidays = _index(data)
    intervals: list[Interval] = []
    for offset in range(days):
        intervals += _spans_for_day(
            first_day + timedelta(days=offset), zone, weekly, holidays
        )

    return _merge(intervals)


def _spans_for_day(
    day: date,
    zone: ZoneInfo,
    weekly: dict[int, dict[str, Any]],
    holidays: dict[str, dict[str, Any]],
) -> list[Interval]:
    """Intervals that START on ``day`` (holiday override applied), unmerged."""
    holiday = holidays.get(day.isoformat())
    override = holiday.get("overrideType") if holiday else None
    if override == "closed":
        return []
    if override == "custom" and holiday is not None:
        return _day_intervals(
            day,
            zone,
            parse_time(holiday.get("openTime")),
            parse_time(holiday.get("closeTime")),
            None,
            None,
        )
    row = weekly.get(day.isoweekday())
    if row is None or row.get("isClosed"):
        return []
    return _day_intervals(
        day,
        zone,
        parse_time(row.get("openTime")),
        parse_time(row.get("closeTime")),
        parse_time(row.get("breakStart")),
        parse_time(row.get("breakEnd")),
    )


def _index(data: dict[str, Any]) -> tuple[ZoneInfo, dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    zone = get_zone(data.get("timezone"))
    weekly = {
        row["dayOfWeek"]: row
        for row in data.get("openingHours", [])
        if isinstance(row, dict) and "dayOfWeek" in row
    }
    holidays = {
        h["date"]: h
        for h in data.get("holidayHours", [])
        if isinstance(h, dict) and h.get("date")
    }
    return zone, weekly, holidays


def describe_day(data: dict[str, Any], day: date) -> str:
    """Human text for one date: ``09:00-12:00, 13:00-17:00`` / Closed / Open 24 hours."""
    zone, weekly, holidays = _index(data)
    spans = _spans_for_day(day, zone, weekly, holidays)
    if not spans:
        return "Closed"
    parts: list[str] = []
    for iv in spans:
        if iv.end - iv.start >= timedelta(days=1) - timedelta(hours=1) and iv.start.timetz() == iv.end.timetz():
            return "Open 24 hours"
        parts.append(f"{iv.start:%H:%M}-{iv.end:%H:%M}")
    return ", ".join(parts)


def _merge(intervals: list[Interval]) -> list[Interval]:
    """Sort and merge touching/overlapping intervals (e.g. back-to-back 24h days)."""
    merged: list[Interval] = []
    for iv in sorted(intervals, key=lambda i: i.start):
        if merged and iv.start <= merged[-1].end:
            if iv.end > merged[-1].end:
                merged[-1] = Interval(merged[-1].start, iv.end)
        else:
            merged.append(iv)
    return merged


@dataclass(frozen=True, slots=True)
class Status:
    """Result of evaluating the schedule at a point in time."""

    is_open: bool
    next_change: datetime | None


def evaluate(data: dict[str, Any], now: datetime, horizon_days: int) -> Status:
    """Return whether the business is open at ``now`` and when that next flips."""
    zone = get_zone(data.get("timezone"))
    local_now = now.astimezone(zone)
    # Start one day back so an overnight span that began yesterday is included.
    intervals = build_intervals(
        data, local_now.date() - timedelta(days=1), horizon_days + 1
    )
    for iv in intervals:
        if iv.start <= local_now < iv.end:
            return Status(True, iv.end)
    upcoming = [iv.start for iv in intervals if iv.start > local_now]
    return Status(False, min(upcoming) if upcoming else None)


def next_local_midnight(data: dict[str, Any], now: datetime) -> datetime:
    """The next midnight in the business timezone (when "today" rolls over)."""
    zone = get_zone(data.get("timezone"))
    local = now.astimezone(zone)
    return datetime.combine(local.date() + timedelta(days=1), time(0), tzinfo=zone)
