"""Deterministic date-phrase resolution (TASK 8.4).

Weeks start on Monday. "next week" = Monday-Friday of the following week. "next Friday" =
the first Friday after today. A date without a year means 2026. Past or ambiguous dates
come back with an "error" so the agent asks the user.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from app.ingestion.holidays import MONTHS

DEFAULT_YEAR = 2026
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_RE})\.?(?:,?\s+(\d{{4}}))?\b", re.IGNORECASE)
_MONTH_DAY = re.compile(rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b", re.IGNORECASE)
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def first_weekday_after(today: date, weekday: int) -> date:
    delta = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=delta)


def _single(phrase: str, today: date) -> tuple[date | None, str | None]:
    p = phrase.strip().lower()
    if p in ("today",):
        return today, None
    if p in ("tomorrow",):
        return today + timedelta(days=1), None
    if p in ("day after tomorrow", "the day after tomorrow"):
        return today + timedelta(days=2), None
    m = re.fullmatch(r"(?:next|this|coming|this coming|on)?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
                     p)
    if m:
        return first_weekday_after(today, WEEKDAYS.index(m.group(1))), None
    m = _ISO.search(p)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), None
        except ValueError:
            return None, "invalid date"
    for rx, d_idx, m_idx in ((_DAY_MONTH, 1, 2), (_MONTH_DAY, 2, 1)):
        m = rx.search(p)
        if m:
            year = int(m.group(3)) if m.group(3) else DEFAULT_YEAR
            try:
                return date(year, MONTHS[m.group(m_idx).lower()], int(m.group(d_idx))), None
            except ValueError:
                return None, "invalid date"
    return None, "unrecognized"


def resolve_dates(phrase: str, today: date) -> dict:
    p = (phrase or "").strip().lower()
    if not p:
        return {"error": "empty phrase"}
    if p in ("next week",):
        monday = today - timedelta(days=today.weekday()) + timedelta(days=7)
        return {"start_date": monday.isoformat(), "end_date": (monday + timedelta(days=4)).isoformat()}
    if p in ("this week",):
        monday = today - timedelta(days=today.weekday())
        start = max(today, monday)
        friday = monday + timedelta(days=4)
        if start > friday:
            return {"error": "ambiguous: this week's working days have passed"}
        return {"start_date": start.isoformat(), "end_date": friday.isoformat()}
    parts = re.split(r"\s+(?:to|until|till|through|-|–)\s+", p, maxsplit=1)
    if len(parts) == 2:
        # "3 to 5 March" -> borrow the month from the right side
        left, right = parts
        if re.fullmatch(r"\d{1,2}(?:st|nd|rd|th)?", left.strip()):
            m = re.search(rf"({_MONTH_RE}).*", right)
            if m:
                left = f"{left} {m.group(0)}"
        start, e1 = _single(left, today)
        end, e2 = _single(right, today)
        if e1 or e2 or not start or not end:
            return {"error": f"could not understand '{phrase}'"}
        if end < start:
            return {"error": "end date is before start date"}
    else:
        start, err = _single(p, today)
        if err or not start:
            return {"error": f"could not understand '{phrase}'"}
        end = start
    if start < today:
        return {"error": f"{start.isoformat()} has already passed", "start_date": start.isoformat(),
                "end_date": end.isoformat()}
    return {"start_date": start.isoformat(), "end_date": end.isoformat()}


def calendar_lines(today: date, weeks: int = 6) -> str:
    monday = today - timedelta(days=today.weekday())
    lines = []
    for w in range(weeks):
        start = monday + timedelta(days=7 * w)
        days = [start + timedelta(days=i) for i in range(7)]
        label = "this week" if w == 0 else ("next week" if w == 1 else f"week +{w}")
        lines.append(f"{label}: " + ", ".join(f"{d.strftime('%a')} {d.isoformat()}" for d in days))
    return "\n".join(lines)


_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def past_reference_date(message: str, today: date) -> date | None:
    """The past date a question is about ("in 2025", "on 1 August 2025"), else None.

    A full past date wins; a bare past year means the last day of that year.
    """
    from app.ingestion.holidays import parse_date

    full = parse_date(message or "")
    if full and full < today:
        return full
    years = [int(m.group(0)) for m in _YEAR.finditer(message or "")]
    past = [y for y in years if y < today.year]
    return date(max(past), 12, 31) if past else None
