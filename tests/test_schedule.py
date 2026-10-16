"""Tests for the pure schedule logic."""

from __future__ import annotations

from datetime import datetime, timezone

from custom_components.selected_with_trust.schedule import evaluate, parse_time

AMS = "Europe/Amsterdam"


def day(dow, o=None, c=None, closed=False, bs=None, be=None):
    return {"dayOfWeek": dow, "isClosed": closed, "openTime": o, "closeTime": c,
            "breakStart": bs, "breakEnd": be}


def utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_parse_time() -> None:
    assert parse_time("09:30").hour == 9
    assert parse_time(None) is None
    assert parse_time("x") is None


def base(rows, holidays=None):
    return {"timezone": AMS, "openingHours": rows, "holidayHours": holidays or []}


# 2026-10-12 is a Monday. Amsterdam is UTC+2 (CEST) until Oct 25.
def test_open_during_day_and_next_change() -> None:
    data = base([day(1, "09:00", "17:00")])
    s = evaluate(data, utc(2026, 10, 12, 8), 14)  # 10:00 local
    assert s.is_open
    assert s.next_change == datetime(2026, 10, 12, 17, tzinfo=s.next_change.tzinfo)


def test_closed_before_opening_points_to_opening() -> None:
    data = base([day(1, "09:00", "17:00")])
    s = evaluate(data, utc(2026, 10, 12, 5), 14)  # 07:00 local
    assert not s.is_open
    assert (s.next_change.hour, s.next_change.day) == (9, 12)


def test_break_closes_midday() -> None:
    data = base([day(1, "09:00", "17:00", bs="12:00", be="13:00")])
    assert not evaluate(data, utc(2026, 10, 12, 10, 30), 14).is_open  # 12:30 local
    assert evaluate(data, utc(2026, 10, 12, 12), 14).is_open  # 14:00 local


def test_overnight_spills_into_next_day() -> None:
    data = base([day(1, "17:30", "01:00")])
    assert evaluate(data, utc(2026, 10, 12, 22), 14).is_open  # 00:00 local Tue
    assert not evaluate(data, utc(2026, 10, 12, 23, 30), 14).is_open  # 01:30 local Tue


def test_24h_day_is_open_all_day() -> None:
    data = base([day(1, "00:00", "00:00")])
    assert evaluate(data, utc(2026, 10, 12, 3), 14).is_open
    s = evaluate(data, utc(2026, 10, 12, 21), 14)  # 23:00 local, ends midnight
    assert s.is_open and s.next_change.day == 13


def test_back_to_back_24h_days_merge() -> None:
    data = base([day(1, "00:00", "00:00"), day(2, "00:00", "00:00")])
    s = evaluate(data, utc(2026, 10, 12, 3), 14)
    assert s.next_change.day == 14  # end of Tuesday, not midnight Monday


def test_closed_flag_and_missing_day() -> None:
    data = base([day(1, closed=True)])
    s = evaluate(data, utc(2026, 10, 12, 10), 14)
    assert not s.is_open and s.next_change is None


def test_holiday_closed_overrides_weekly() -> None:
    data = base([day(1, "09:00", "17:00")],
                [{"date": "2026-10-12", "overrideType": "closed"}])
    s = evaluate(data, utc(2026, 10, 12, 10), 14)
    assert not s.is_open
    assert s.next_change.day == 19  # next Monday


def test_holiday_custom_hours() -> None:
    data = base([day(1, "09:00", "17:00")],
                [{"date": "2026-10-12", "overrideType": "custom",
                  "openTime": "10:00", "closeTime": "12:00"}])
    assert evaluate(data, utc(2026, 10, 12, 8, 30), 14).is_open  # 10:30 local
    assert not evaluate(data, utc(2026, 10, 12, 12), 14).is_open  # 14:00 local


def test_holiday_regular_or_null_uses_weekly() -> None:
    for ov in ("regular", None):
        data = base([day(1, "09:00", "17:00")],
                    [{"date": "2026-10-12", "overrideType": ov}])
        assert evaluate(data, utc(2026, 10, 12, 8), 14).is_open


def test_timezone_is_business_not_utc() -> None:
    data = {"timezone": "America/New_York",
            "openingHours": [day(1, "09:00", "17:00")], "holidayHours": []}
    assert evaluate(data, utc(2026, 10, 12, 14), 14).is_open  # 10:00 EDT
    assert not evaluate(data, utc(2026, 10, 12, 8), 14).is_open  # 04:00 EDT


def test_bad_timezone_falls_back() -> None:
    data = {"timezone": "Nope/Zone", "openingHours": [day(1, "09:00", "17:00")]}
    assert evaluate(data, utc(2026, 10, 12, 8), 14).is_open


def test_describe_day() -> None:
    from datetime import date

    from custom_components.selected_with_trust.schedule import (
        describe_day,
        next_local_midnight,
    )

    data = base(
        [day(1, "09:00", "17:00", bs="12:00", be="13:00"), day(2, "00:00", "00:00"),
         day(3, "17:30", "01:00"), day(4, closed=True)],
        [{"date": "2026-10-19", "overrideType": "closed"}],
    )
    assert describe_day(data, date(2026, 10, 12)) == "09:00-12:00, 13:00-17:00"
    assert describe_day(data, date(2026, 10, 13)) == "Open 24 hours"
    assert describe_day(data, date(2026, 10, 14)) == "17:30-01:00"
    assert describe_day(data, date(2026, 10, 15)) == "Closed"
    assert describe_day(data, date(2026, 10, 19)) == "Closed"  # holiday
    assert describe_day(data, date(2026, 10, 17)) == "Closed"  # no row
    assert next_local_midnight(data, utc(2026, 10, 12, 8)).day == 13
