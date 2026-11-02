"""Requester identity: the X-Employee-Id header + the database record, nothing else (TASK 7.1)."""

from __future__ import annotations

from app.data import repositories as repo
from app.data import state
from app.data.repositories import Employee


class AuthError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def resolve_requester(header_value: str | None) -> Employee:
    """401 if the header is missing or the employee is not in the database."""
    employee_id = (header_value or "").strip()
    if not employee_id:
        raise AuthError(401, "X-Employee-Id header is required")
    employee = repo.get_employee(employee_id)
    if employee is None:
        raise AuthError(401, "Unknown employee")
    return employee


def check_session_owner(session_id: str, employee: Employee) -> None:
    """A session belongs to whoever sent its first message; anyone else gets 403."""
    if not state.claim_session(session_id, employee.employee_id):
        raise AuthError(403, "This session belongs to another employee")
