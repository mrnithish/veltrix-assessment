"""Extract holiday dates from calendar documents' tables during ingestion.

Generic: any table row that holds a parseable date and a name becomes a holiday.
Tables under a heading (or with a header) mentioning restricted/optional/floating holidays
are stored with kind="restricted" and are NOT used for working-day calculation, because the
office stays open on those days.
"""

from __future__ import annotations

import re
from datetime import date

from app.ingestion.models import Block, DocMeta

MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",),
            ("june", "jun"), ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"),
            ("october", "oct"), ("november", "nov"), ("december", "dec"),
        ]
    )
    for m in names
}
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_RE})\.?,?\s+(\d{{4}})\b", re.IGNORECASE)
_MDY = re.compile(rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.IGNORECASE)
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DOTTED = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")  # German style 03.10.2026
_WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
_RESTRICTED = re.compile(r"restricted|optional|floating", re.IGNORECASE)


def parse_date(text: str) -> date | None:
    text = text or ""
    for rx, order in ((_ISO, "ymd"), (_DMY, "dmy"), (_MDY, "mdy"), (_DOTTED, "dmy_num")):
        m = rx.search(text)
        if not m:
            continue
        try:
            if order == "ymd":
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if order == "dmy":
                return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
            if order == "mdy":
                return date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
    return None


def _name_from_row(row: list[str], date_col: int) -> str:
    candidates = []
    for i, cell in enumerate(row):
        c = cell.strip()
        if i == date_col or not c or c.lower() in _WEEKDAYS or parse_date(c):
            continue
        candidates.append(c)
    return max(candidates, key=len) if candidates else ""


def extract_holidays(meta: DocMeta, blocks: list[Block]) -> list[dict]:
    if meta.doc_type != "calendar":
        return []
    out: list[dict] = []
    heading = ""
    for block in blocks:
        if block.kind == "heading":
            heading = block.text
            continue
        if block.kind != "table" or not block.rows:
            continue
        header = " ".join(block.rows[0])
        kind = "restricted" if _RESTRICTED.search(heading) or _RESTRICTED.search(header) else "public"
        for row in block.rows:
            date_col, found = -1, None
            for i, cell in enumerate(row):
                found = parse_date(cell)
                if found:
                    date_col = i
                    break
            if not found:
                continue
            out.append(
                {"doc_id": meta.doc_id, "date": found.isoformat(), "name": _name_from_row(row, date_col) or "Holiday",
                 "kind": kind}
            )
    return out
