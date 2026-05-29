from datetime import date

import pytest

from mockwork.calendar import parse_date, weekly_meeting_days, workdays_between, workweeks_between


def test_workdays_between_skips_weekends():
    days = workdays_between(date(2026, 5, 22), date(2026, 5, 26))

    assert days == [
        date(2026, 5, 22),
        date(2026, 5, 25),
        date(2026, 5, 26),
    ]


def test_weekly_meeting_days_uses_last_workday_per_iso_week():
    days = workdays_between(date(2026, 5, 18), date(2026, 5, 29))

    assert weekly_meeting_days(days) == {date(2026, 5, 22), date(2026, 5, 29)}


def test_workweeks_between_groups_workdays_by_iso_week():
    weeks = workweeks_between(date(2026, 5, 22), date(2026, 5, 26))

    assert weeks == [
        {
            "week_id": "2026-W21",
            "start_date": "2026-05-22",
            "end_date": "2026-05-22",
            "workdays": ["2026-05-22"],
        },
        {
            "week_id": "2026-W22",
            "start_date": "2026-05-25",
            "end_date": "2026-05-26",
            "workdays": ["2026-05-25", "2026-05-26"],
        },
    ]


def test_parse_date_rejects_invalid_format():
    with pytest.raises(ValueError):
        parse_date("2026/05/25")
