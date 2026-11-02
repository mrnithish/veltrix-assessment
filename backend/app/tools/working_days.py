"""Working days = Monday-Friday dates that are not public holidays for the requester's region.

Holidays come from the holiday-calendar document that applies to the requester (TASK 5 rules:
readable, for their region, effective, highest precedence), extracted at ingestion.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.ingestion.models import DocMeta
from app.retrieval.eligibility import Requester, is_eligible
from app.retrieval.precedence import precedence_key


def applicable_calendar(docs: dict[str, DocMeta], holidays: dict, requester: Requester, year: int) -> DocMeta | None:
    """The calendar that applies for ``year``: eligible by the end of that year and listing dates in it."""
    ref = date(year, 12, 31)
    candidates = [
        d for d in docs.values()
        if d.doc_type == "calendar"
        and is_eligible(d, requester, ref)
        and any(h.date.year == year for h in holidays.get(d.doc_id, []))
    ]
    return max(candidates, key=precedence_key) if candidates else None


def public_holidays(docs, holidays, requester: Requester, start: date, end: date) -> dict[date, tuple[str, str]]:
    """{date: (holiday name, calendar doc_id)} for public holidays in [start, end]."""
    out: dict[date, tuple[str, str]] = {}
    for year in range(start.year, end.year + 1):
        cal = applicable_calendar(docs, holidays, requester, year)
        if cal is None:
            continue
        for h in holidays.get(cal.doc_id, []):
            if h.kind == "public" and start <= h.date <= end:
                out[h.date] = (h.name, cal.doc_id)
    return out


def count_working_days(start: date, end: date, holiday_dates: set[date] | dict) -> int:
    if end < start:
        return 0
    days, d = 0, start
    while d <= end:
        if d.weekday() < 5 and d not in holiday_dates:
            days += 1
        d += timedelta(days=1)
    return days
