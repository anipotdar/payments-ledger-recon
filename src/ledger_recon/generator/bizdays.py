"""Business-day arithmetic for settlement value dates."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta


def is_business_day(d: date, holidays: Iterable[date]) -> bool:
    return d.weekday() < 5 and d not in set(holidays)


def add_business_days(d: date, n: int, holidays: Iterable[date]) -> date:
    """Move forward n business days. n=1 from a Friday lands on Monday."""
    hol = set(holidays)
    cur = d
    added = 0
    while added < n:
        cur += timedelta(days=1)
        if cur.weekday() < 5 and cur not in hol:
            added += 1
    return cur


def days_between(start: date, end: date) -> list[date]:
    """Inclusive list of calendar days."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]
