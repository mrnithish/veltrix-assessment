"""Leave-data access per role, for every tool."""

from app.tools.permissions import BULK_MESSAGE, NOT_ALLOWED_MESSAGE
from tests.conftest import make_ctx


def test_employee_sees_own_balance(corpus):
    rec = make_ctx("E201", corpus).get_leave_balance("E201")
    assert rec.status == "success" and rec.result["balances"] == {"annual": 10.0, "sick": 8.0}


def test_employee_cannot_see_colleague(corpus):
    rec = make_ctx("E201", corpus).get_leave_balance("E202")
    assert rec.status == "error" and rec.error == NOT_ALLOWED_MESSAGE and rec.error_kind == "permission"


def test_same_refusal_for_unknown_and_forbidden_employee(corpus):
    ctx = make_ctx("E201", corpus)
    forbidden = ctx.get_leave_balance("E400")
    unknown = ctx.list_leave_requests("E999")
    assert forbidden.error == unknown.error == NOT_ALLOWED_MESSAGE


def test_manager_sees_direct_report_only(corpus):
    ctx = make_ctx("E200", corpus)
    assert ctx.list_leave_requests("E201").status == "success"
    other = make_ctx("E200", corpus).get_leave_balance("E301")  # another manager's report
    assert other.error == NOT_ALLOWED_MESSAGE


def test_manager_cannot_see_own_manager_or_peers(corpus):
    assert make_ctx("E200", corpus).get_leave_balance("E300").error == NOT_ALLOWED_MESSAGE


def test_hr_sees_any_one_employee(corpus):
    assert make_ctx("E100", corpus).get_leave_balance("E400").status == "success"
    assert make_ctx("E100", corpus).get_leave_balance("E999").error == NOT_ALLOWED_MESSAGE


def test_bulk_access_is_refused_for_every_role(corpus):
    hr = make_ctx("E100", corpus)
    assert hr.get_leave_balance("E201").status == "success"
    second = hr.get_leave_balance("E301")
    assert second.error == BULK_MESSAGE and second.error_kind == "bulk"
    mgr = make_ctx("E200", corpus)
    mgr.get_leave_balance("E201")
    assert mgr.list_leave_requests("E202").error_kind == "bulk"


def test_same_other_employee_twice_is_fine(corpus):
    hr = make_ctx("E100", corpus)
    assert hr.get_leave_balance("E201").status == "success"
    assert hr.list_leave_requests("E201").status == "success"


def test_team_leave_managers_only(corpus):
    assert make_ctx("E201", corpus).get_team_leave("2026-06-01", "2026-12-31").error_kind == "permission"
    assert make_ctx("E100", corpus).get_team_leave("2026-06-01", "2026-12-31").error_kind == "permission"


def test_team_leave_returns_direct_reports_overlapping(corpus):
    rec = make_ctx("E200", corpus).get_team_leave("2026-07-01", "2026-08-31")
    assert rec.status == "success"
    rows = rec.result["team_leave"]
    assert {r["request_id"] for r in rows} == {"req-e201-jul", "req-e201-aug"}  # cancelled one excluded
    assert all(r["employee_id"] in ("E201", "E202") for r in rows)


def test_identity_comes_from_context_not_arguments(corpus):
    # apply/cancel have no employee argument: they always act for the requester
    ctx = make_ctx("E201", corpus)
    rec = ctx.cancel_leave("req-e301-jul")  # someone else's request
    assert rec.status == "error" and "couldn't find" in rec.error


def test_invalid_leave_type_and_status(corpus):
    ctx = make_ctx("E201", corpus)
    assert ctx.get_leave_balance("E201", "vacation").status == "error"
    assert ctx.list_leave_requests("E201", "rejected").status == "error"
