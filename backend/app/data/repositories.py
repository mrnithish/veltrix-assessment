"""Data access for veltrix.db. Existing tables/columns are never altered.

Functions here do no permission checks; callers in app/tools/ do.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.data.db import hr_db, transaction

ACTIVE_STATUSES = ("pending", "approved")


@dataclass(frozen=True)
class Employee:
    employee_id: str
    full_name: str
    email: str
    phone: str
    region: str
    join_date: str
    level: str
    role: str
    manager_id: str | None


def get_employee(employee_id: str) -> Employee | None:
    if not employee_id:
        return None
    with hr_db() as conn:
        row = conn.execute("SELECT * FROM employees WHERE employee_id = ?", (employee_id,)).fetchone()
    return Employee(**dict(row)) if row else None


def list_employees() -> list[Employee]:
    with hr_db() as conn:
        rows = conn.execute("SELECT * FROM employees ORDER BY employee_id").fetchall()
    return [Employee(**dict(r)) for r in rows]


def direct_report_ids(manager_id: str) -> list[str]:
    with hr_db() as conn:
        rows = conn.execute(
            "SELECT employee_id FROM employees WHERE manager_id = ? ORDER BY employee_id", (manager_id,)
        ).fetchall()
    return [r["employee_id"] for r in rows]


def get_balances(employee_id: str, leave_type: str | None = None) -> list[dict]:
    sql = "SELECT leave_type, balance_days FROM leave_balances WHERE employee_id = ?"
    params: list = [employee_id]
    if leave_type:
        sql += " AND leave_type = ?"
        params.append(leave_type)
    with hr_db() as conn:
        rows = conn.execute(sql + " ORDER BY leave_type", params).fetchall()
    return [dict(r) for r in rows]


def list_requests(employee_id: str, status: str | None = None) -> list[dict]:
    sql = (
        "SELECT request_id, leave_type, start_date, end_date, working_days, status, created_at "
        "FROM leave_requests WHERE employee_id = ?"
    )
    params: list = [employee_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    with hr_db() as conn:
        rows = conn.execute(sql + " ORDER BY start_date, created_at", params).fetchall()
    return [dict(r) for r in rows]


def get_request(request_id: str) -> dict | None:
    with hr_db() as conn:
        row = conn.execute("SELECT * FROM leave_requests WHERE request_id = ?", (request_id,)).fetchone()
    return dict(row) if row else None


def team_leave(manager_id: str, start_date: str, end_date: str) -> list[dict]:
    """Pending/approved leave of the manager's direct reports overlapping [start, end]."""
    with hr_db() as conn:
        rows = conn.execute(
            """
            SELECT r.request_id, r.employee_id, e.full_name, r.leave_type, r.start_date, r.end_date,
                   r.working_days, r.status
            FROM leave_requests r JOIN employees e ON e.employee_id = r.employee_id
            WHERE e.manager_id = ? AND r.status IN ('pending', 'approved')
              AND r.start_date <= ? AND r.end_date >= ?
            ORDER BY r.start_date, r.employee_id
            """,
            (manager_id, end_date, start_date),
        ).fetchall()
    return [dict(r) for r in rows]


def overlapping_active_requests(conn, employee_id: str, start_date: str, end_date: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT request_id, start_date, end_date, status FROM leave_requests
        WHERE employee_id = ? AND status IN ('pending', 'approved') AND start_date <= ? AND end_date >= ?
        """,
        (employee_id, end_date, start_date),
    ).fetchall()
    return [dict(r) for r in rows]


def balance_in_tx(conn, employee_id: str, leave_type: str) -> float | None:
    row = conn.execute(
        "SELECT balance_days FROM leave_balances WHERE employee_id = ? AND leave_type = ?",
        (employee_id, leave_type),
    ).fetchone()
    return None if row is None else float(row["balance_days"])


class WriteConflict(Exception):
    """Raised inside a write transaction when the data changed since validation."""


def create_request_and_debit(
    employee_id: str, leave_type: str, start_date: str, end_date: str, working_days: int, recheck
) -> str:
    """One transaction: re-check rules (via ``recheck(conn)``), insert pending request, subtract balance."""
    request_id = str(uuid.uuid4())
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "")
    with hr_db() as conn, transaction(conn):
        recheck(conn)
        conn.execute(
            "INSERT INTO leave_requests (request_id, employee_id, leave_type, start_date, end_date, "
            "working_days, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
            (request_id, employee_id, leave_type, start_date, end_date, working_days, created_at),
        )
        cur = conn.execute(
            "UPDATE leave_balances SET balance_days = balance_days - ? WHERE employee_id = ? AND leave_type = ?",
            (working_days, employee_id, leave_type),
        )
        if cur.rowcount != 1:
            raise WriteConflict("No balance record exists for this leave type.")
    return request_id


def cancel_request_and_credit(request_id: str, recheck) -> dict:
    """One transaction: re-check rules, set status cancelled, add working_days back."""
    with hr_db() as conn, transaction(conn):
        row = conn.execute("SELECT * FROM leave_requests WHERE request_id = ?", (request_id,)).fetchone()
        req = dict(row) if row else None
        recheck(conn, req)
        conn.execute("UPDATE leave_requests SET status = 'cancelled' WHERE request_id = ?", (request_id,))
        conn.execute(
            "UPDATE leave_balances SET balance_days = balance_days + ? WHERE employee_id = ? AND leave_type = ?",
            (req["working_days"], req["employee_id"], req["leave_type"]),
        )
    return req
