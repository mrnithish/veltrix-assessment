"""apply_leave / cancel_leave rules (TASK 6.2, 6.3). Today is Mon 2026-06-15."""

import sqlite3
import uuid

from app.config import get_settings
from tests.conftest import make_ctx


def balance(emp: str, lt: str) -> float:
    conn = sqlite3.connect(get_settings().db_path)
    v = conn.execute("SELECT balance_days FROM leave_balances WHERE employee_id=? AND leave_type=?",
                     (emp, lt)).fetchone()[0]
    conn.close()
    return v


def request_row(rid: str):
    conn = sqlite3.connect(get_settings().db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM leave_requests WHERE request_id=?", (rid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def propose_and_execute(ctx, lt, start, end):
    rec = ctx.apply_leave(lt, start, end)
    assert rec.status == "pending_confirmation", rec.error
    return ctx.execute_proposal({"name": "apply_leave", "args": {"leave_type": lt, "start_date": start,
                                                                 "end_date": end},
                                 "employee_id": ctx.employee.employee_id})


def test_proposal_counts_working_days_and_changes_nothing(corpus):
    ctx = make_ctx("E201", corpus)
    rec = ctx.apply_leave("annual", "2026-06-17", "2026-06-23")  # Wed..Tue, Fri 19 Jun is an IN holiday
    assert rec.status == "pending_confirmation"
    assert rec.result["proposal"]["working_days"] == 4
    assert balance("E201", "annual") == 10


def test_execute_creates_pending_request_and_debits_balance(corpus):
    rec = propose_and_execute(make_ctx("E201", corpus), "annual", "2026-06-17", "2026-06-23")
    assert rec.status == "success"
    row = request_row(rec.result["request_id"])
    assert row["status"] == "pending" and row["working_days"] == 4
    assert uuid.UUID(row["request_id"]).version == 4
    assert balance("E201", "annual") == 6


def test_reject_invalid_leave_type(corpus):
    assert make_ctx("E201", corpus).apply_leave("casual", "2026-06-17", "2026-06-17").status == "error"


def test_reject_outside_2026(corpus):
    rec = make_ctx("E201", corpus).apply_leave("annual", "2026-12-30", "2027-01-02")
    assert rec.status == "error" and "2026" in rec.error


def test_reject_past_start(corpus):
    rec = make_ctx("E201", corpus).apply_leave("annual", "2026-06-12", "2026-06-17")
    assert rec.status == "error" and "passed" in rec.error and rec.error_kind == "past_date"


def test_start_today_is_allowed(corpus):
    rec = make_ctx("E202", corpus).apply_leave("annual", "2026-06-15", "2026-06-15")
    assert rec.status == "pending_confirmation"


def test_reject_end_before_start(corpus):
    assert make_ctx("E201", corpus).apply_leave("annual", "2026-06-20", "2026-06-18").status == "error"


def test_reject_zero_working_days(corpus):
    rec = make_ctx("E201", corpus).apply_leave("annual", "2026-06-20", "2026-06-21")  # weekend
    assert rec.status == "error" and "no working days" in rec.error


def test_reject_holiday_only(corpus):
    rec = make_ctx("E201", corpus).apply_leave("annual", "2026-06-19", "2026-06-19")  # IN public holiday
    assert rec.status == "error" and "no working days" in rec.error


def test_reject_exceeding_balance(corpus):
    rec = make_ctx("E202", corpus).apply_leave("annual", "2026-06-16", "2026-06-18")  # 3 days > 2
    assert rec.status == "error" and "balance" in rec.error


def test_reject_overlap_with_pending_or_approved(corpus):
    rec = make_ctx("E201", corpus).apply_leave("annual", "2026-08-04", "2026-08-05")
    assert rec.status == "error" and "overlap" in rec.error


def test_overlap_with_cancelled_is_fine(corpus):
    rec = make_ctx("E201", corpus).apply_leave("annual", "2026-09-01", "2026-09-01")
    assert rec.status == "pending_confirmation"


def test_execute_rechecks_rules(corpus):
    ctx = make_ctx("E201", corpus)
    assert propose_and_execute(ctx, "annual", "2026-06-17", "2026-06-17").status == "success"
    again = propose_and_execute_unchecked(make_ctx("E201", corpus), "annual", "2026-06-17", "2026-06-17")
    assert again.status == "error" and "overlap" in again.error
    assert balance("E201", "annual") == 9


def propose_and_execute_unchecked(ctx, lt, start, end):
    return ctx.execute_proposal({"name": "apply_leave", "args": {"leave_type": lt, "start_date": start,
                                                                 "end_date": end},
                                 "employee_id": ctx.employee.employee_id})


def test_cancel_future_request_restores_balance(corpus):
    ctx = make_ctx("E201", corpus)
    assert ctx.cancel_leave("req-e201-aug").status == "pending_confirmation"
    rec = ctx.execute_proposal({"name": "cancel_leave", "args": {"request_id": "req-e201-aug"},
                                "employee_id": "E201"})
    assert rec.status == "success"
    assert request_row("req-e201-aug")["status"] == "cancelled"
    assert balance("E201", "annual") == 12


def test_cannot_cancel_started_or_past_request(corpus):
    ctx = make_ctx("E201", corpus)
    assert ctx.cancel_leave("req-e201-today").status == "error"  # starts today, not after today
    assert ctx.cancel_leave("req-e201-past").status == "error"


def test_cannot_cancel_cancelled_request(corpus):
    rec = make_ctx("E201", corpus).cancel_leave("req-e201-sep")
    assert rec.status == "error" and "cancelled" in rec.error


def test_cannot_cancel_someone_elses_request(corpus):
    rec = make_ctx("E200", corpus).cancel_leave("req-e201-aug")  # even their manager
    assert rec.status == "error"
    assert request_row("req-e201-aug")["status"] == "pending"


def test_proposal_of_another_employee_is_never_executed(corpus):
    import pytest

    ctx = make_ctx("E202", corpus)
    with pytest.raises(PermissionError):
        ctx.execute_proposal({"name": "cancel_leave", "args": {"request_id": "req-e201-aug"}, "employee_id": "E201"})
