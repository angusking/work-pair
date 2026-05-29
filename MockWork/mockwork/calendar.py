from __future__ import annotations

from datetime import date, timedelta


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid date '{value}', expected YYYY-MM-DD") from exc


def workdays_between(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("end date must be on or after start date")

    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def weekly_meeting_days(workdays: list[date]) -> set[date]:
    """Return the last workday in each ISO week."""
    by_week: dict[tuple[int, int], date] = {}
    for day in workdays:
        iso = day.isocalendar()
        by_week[(iso.year, iso.week)] = day
    return set(by_week.values())


def workweeks_between(start: date, end: date) -> list[dict[str, object]]:
    """Return workdays grouped by ISO week."""
    grouped: dict[tuple[int, int], list[date]] = {}
    for day in workdays_between(start, end):
        iso = day.isocalendar()
        grouped.setdefault((iso.year, iso.week), []).append(day)

    weeks: list[dict[str, object]] = []
    for year, week in sorted(grouped):
        days = grouped[(year, week)]
        weeks.append(
            {
                "week_id": f"{year}-W{week:02d}",
                "start_date": days[0].isoformat(),
                "end_date": days[-1].isoformat(),
                "workdays": [day.isoformat() for day in days],
            }
        )
    return weeks
