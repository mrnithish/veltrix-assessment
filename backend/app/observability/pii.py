"""Personal-data protection: masking for answers/tool args and scrubbing for logs/traces.

Personal data = full_name, email, phone of employees (TASK 7.4).
"""

from __future__ import annotations

import re
import threading
from typing import Any

_EMAIL = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
# International-looking phone numbers: optional +, 9-15 digits with separators.
_PHONE = re.compile(r"(?<![\w-])\+?\(?\d[\d\s().-]{7,}\d(?![\w-])")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

_lock = threading.Lock()
_names: dict[str, str] = {}  # full_name -> employee_id
_emails: dict[str, str] = {}  # lower email -> employee_id
_phone_digits: dict[str, str] = {}  # digits -> employee_id


def register_people(employees) -> None:
    """Load the people registry from the DB so scrubbers can recognise names/emails/phones."""
    names, emails, phones = {}, {}, {}
    for e in employees:
        if e.full_name:
            names[e.full_name] = e.employee_id
        if e.email:
            emails[e.email.lower()] = e.employee_id
        digits = re.sub(r"\D", "", e.phone or "")
        if len(digits) >= 7:
            phones[digits] = e.employee_id
    with _lock:
        _names.clear(), _names.update(names)
        _emails.clear(), _emails.update(emails)
        _phone_digits.clear(), _phone_digits.update(phones)


def mask_email(email: str) -> str:
    m = _EMAIL.fullmatch(email.strip())
    if not m:
        return email
    return f"{m.group(1)}***@{m.group(2)}"


def _strip_phones(text: str) -> str:
    def repl(m: re.Match) -> str:
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        with _lock:
            known = digits in _phone_digits
        if known or (raw.lstrip().startswith("+") and 9 <= len(digits) <= 15):
            return "[phone removed]"
        # Dates, ids and amounts also look like digit runs: only strip clear phone shapes.
        if _ISO_DATE.search(raw) or not 10 <= len(digits) <= 15:
            return raw
        return "[phone removed]"

    return _PHONE.sub(repl, text)


def mask_for_user(text: str, visible_names: set[str] | None = None) -> str:
    """For answers and tool_call args: masked emails, no phones, names only if visible."""
    if not text:
        return text
    text = _EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text)
    text = _strip_phones(text)
    visible = visible_names or set()
    with _lock:
        names = sorted(_names.items(), key=lambda kv: -len(kv[0]))
    for name, emp_id in names:
        if name not in visible and name in text:
            text = text.replace(name, emp_id)
    return text


def scrub_for_logs(text: str) -> str:
    """For logs and traces: no names, emails or phones at all (employee IDs instead)."""
    if not text:
        return text
    with _lock:
        names = sorted(_names.items(), key=lambda kv: -len(kv[0]))
        emails = dict(_emails)

    def email_repl(m: re.Match) -> str:
        emp = emails.get(m.group(0).lower())
        return f"<{emp}:email>" if emp else f"{m.group(1)}***@{m.group(2)}"

    text = _EMAIL.sub(email_repl, text)
    text = _strip_phones(text)
    for name, emp_id in names:
        if name in text:
            text = text.replace(name, emp_id)
    return text


def scrub_obj(value: Any, fn=scrub_for_logs) -> Any:
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, dict):
        return {k: scrub_obj(v, fn) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub_obj(v, fn) for v in value]
    return value
