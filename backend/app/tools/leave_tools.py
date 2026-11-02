"""The five leave tools (TASK 6.1), with permission checks inside the tool code.

The requester is always ``ToolContext.employee``, built from the X-Employee-Id header.
LLM-chosen arguments are never trusted for identity.

apply_leave / cancel_leave called by the agent only *validate and propose*; the write happens
in ``execute_proposal`` after the user confirms in the next message.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date

from app.data import repositories as repo
from app.data import state
from app.data.repositories import Employee, WriteConflict
from app.observability import metrics
from app.observability.logging import get_logger
from app.observability.pii import mask_for_user
from app.observability.tracing import tracer
from app.retrieval.eligibility import Requester
from app.tools.permissions import BULK_MESSAGE, NOT_ALLOWED_MESSAGE, TEAM_ONLY_MANAGERS, can_view_employee
from app.tools.working_days import count_working_days, public_holidays

log = get_logger(__name__)

CONTRACT_TOOLS = ("get_leave_balance", "list_leave_requests", "get_team_leave", "apply_leave", "cancel_leave")
LEAVE_TYPES = ("annual", "sick")
REQUEST_STATUSES = ("pending", "approved", "cancelled")
LEAVE_YEAR = 2026
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class ToolRecord:
    name: str
    args: dict
    status: str  # "success" | "error" | "pending_confirmation"
    result: dict = field(default_factory=dict)
    error: str | None = None
    error_kind: str | None = None  # "permission" | "bulk" | "validation" | "not_found"
    duration_ms: float = 0.0

    def public(self) -> dict:
        """Shape used in the API response (tool_calls)."""
        return {"name": self.name, "args": mask_args(self.args), "status": self.status}


def mask_args(args: dict) -> dict:
    return {k: mask_for_user(v) if isinstance(v, str) else v for k, v in args.items() if v is not None}


class ToolError(Exception):
    def __init__(self, message: str, kind: str = "validation"):
        super().__init__(message)
        self.message = message
        self.kind = kind


def _parse_date(value, name: str) -> date:
    if not isinstance(value, str) or not _ISO.match(value.strip()):
        raise ToolError(f"{name} must be a date in YYYY-MM-DD format.")
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ToolError(f"{name} is not a valid calendar date.") from None


class ToolContext:
    def __init__(self, employee: Employee, request_id: str, today: date, corpus, *, max_other_employees: int = 1):
        self.employee = employee
        self.requester = Requester(employee.employee_id, employee.role, employee.region)
        self.request_id = request_id
        self.today = today
        self.corpus = corpus
        self.records: list[ToolRecord] = []
        self.max_other_employees = max_other_employees
        self._other_targets: set[str] = set()

    # ---- bookkeeping -------------------------------------------------------------------------

    def run(self, name: str, args: dict, fn) -> ToolRecord:
        t0 = time.perf_counter()
        with tracer().start_as_current_span(f"tool.{name}") as span:
            span.set_attribute("tool.name", name)
            span.set_attribute("tool.args", str(mask_args(args)))
            try:
                status, result = fn()
                rec = ToolRecord(name, args, status, result)
            except ToolError as exc:
                rec = ToolRecord(name, args, "error", {}, exc.message, exc.kind)
            rec.duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            span.set_attribute("tool.status", rec.status)
            if rec.error_kind:
                span.set_attribute("tool.error_kind", rec.error_kind)
        self.records.append(rec)
        metrics.TOOL_CALLS.labels(name, rec.status).inc()
        log.info("tool_call", tool=name, args=mask_args(args), status=rec.status, error_kind=rec.error_kind,
                 duration_ms=rec.duration_ms)
        try:
            state.write_audit(self.request_id, self.employee.employee_id, name, mask_args(args), rec.status,
                              rec.error_kind or None)
        except Exception:  # auditing must never break a request
            log.exception("audit_write_failed")
        return rec

    def _check_target(self, target_id: str) -> str:
        target_id = (target_id or "").strip() or self.employee.employee_id
        if not can_view_employee(self.employee, target_id):
            raise ToolError(NOT_ALLOWED_MESSAGE, "permission")
        if target_id != self.employee.employee_id:
            if target_id not in self._other_targets and len(self._other_targets) >= self.max_other_employees:
                raise ToolError(BULK_MESSAGE, "bulk")
            self._other_targets.add(target_id)
        return target_id

    def holidays_between(self, start: date, end: date) -> dict[date, tuple[str, str]]:
        return public_holidays(self.corpus.docs, self.corpus.holidays, self.requester, start, end)

    # ---- read tools --------------------------------------------------------------------------

    def get_leave_balance(self, employee_id: str | None = None, leave_type: str | None = None) -> ToolRecord:
        args = {"employee_id": employee_id, "leave_type": leave_type}

        def fn():
            if leave_type is not None and leave_type not in LEAVE_TYPES:
                raise ToolError("leave_type must be 'annual' or 'sick'.")
            target = self._check_target(employee_id)
            balances = repo.get_balances(target, leave_type)
            return "success", {
                "employee_id": target,
                "balances": {b["leave_type"]: b["balance_days"] for b in balances},
                "note": "Current remaining balance; pending and approved requests are already subtracted.",
            }

        return self.run("get_leave_balance", args, fn)

    def list_leave_requests(self, employee_id: str | None = None, status: str | None = None) -> ToolRecord:
        args = {"employee_id": employee_id, "status": status}

        def fn():
            if status is not None and status not in REQUEST_STATUSES:
                raise ToolError("status must be 'pending', 'approved' or 'cancelled'.")
            target = self._check_target(employee_id)
            return "success", {"employee_id": target, "requests": repo.list_requests(target, status)}

        return self.run("list_leave_requests", args, fn)

    def get_team_leave(self, start_date: str | None = None, end_date: str | None = None) -> ToolRecord:
        args = {"start_date": start_date, "end_date": end_date}

        def fn():
            if self.employee.role != "manager":
                raise ToolError(TEAM_ONLY_MANAGERS, "permission")
            start, end = _parse_date(start_date, "start_date"), _parse_date(end_date, "end_date")
            if end < start:
                raise ToolError("end_date must be on or after start_date.")
            rows = repo.team_leave(self.employee.employee_id, start.isoformat(), end.isoformat())
            return "success", {"start_date": start.isoformat(), "end_date": end.isoformat(), "team_leave": rows}

        return self.run("get_team_leave", args, fn)

    # ---- write tools (validate + propose) ----------------------------------------------------

    def _validate_apply(self, leave_type, start_date, end_date, conn=None) -> dict:
        if leave_type not in LEAVE_TYPES:
            raise ToolError("Leave type must be 'annual' or 'sick'.", "needs_detail")
        start, end = _parse_date(start_date, "start_date"), _parse_date(end_date, "end_date")
        if start.year != LEAVE_YEAR or end.year != LEAVE_YEAR:
            raise ToolError(f"Leave can only be requested for dates in {LEAVE_YEAR}.", "out_of_scope")
        if start < self.today:
            raise ToolError(f"The start date {start.isoformat()} has already passed. Leave must start today "
                            f"({self.today.isoformat()}) or later.", "past_date")
        if end < start:
            raise ToolError("The end date must be on or after the start date.", "needs_detail")
        hols = self.holidays_between(start, end)
        working = count_working_days(start, end, set(hols))
        if working == 0:
            raise ToolError("The selected dates contain no working days (only weekends or public holidays).")
        if conn is None:
            balances = repo.get_balances(self.employee.employee_id, leave_type)
            balance = balances[0]["balance_days"] if balances else None
        else:
            balance = repo.balance_in_tx(conn, self.employee.employee_id, leave_type)
        if balance is None:
            raise ToolError(f"You have no {leave_type} leave balance on record.")
        if working > balance:
            raise ToolError(f"This request needs {working} working days but your {leave_type} leave balance is "
                            f"{balance:g} days.")
        if conn is None:
            from app.data.db import hr_db

            with hr_db() as c:
                overlaps = repo.overlapping_active_requests(c, self.employee.employee_id, start.isoformat(),
                                                            end.isoformat())
        else:
            overlaps = repo.overlapping_active_requests(conn, self.employee.employee_id, start.isoformat(),
                                                        end.isoformat())
        if overlaps:
            o = overlaps[0]
            raise ToolError(f"These dates overlap your existing {o['status']} leave request from {o['start_date']} "
                            f"to {o['end_date']} (request ID {o['request_id']}).")
        return {
            "leave_type": leave_type,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "working_days": working,
            "public_holidays_in_range": [{"date": d.isoformat(), "name": n} for d, (n, _doc) in sorted(hols.items())],
            "balance_before": balance,
            "balance_after": balance - working,
        }

    def apply_leave(self, leave_type: str | None = None, start_date: str | None = None,
                    end_date: str | None = None) -> ToolRecord:
        args = {"leave_type": leave_type, "start_date": start_date, "end_date": end_date}

        def fn():
            proposal = self._validate_apply(leave_type, start_date, end_date)
            return "pending_confirmation", {"proposal": proposal}

        return self.run("apply_leave", args, fn)

    def _validate_cancel(self, request_id, req: dict | None) -> dict:
        if not request_id or not isinstance(request_id, str):
            raise ToolError("Please tell me which leave request to cancel.")
        if req is None or req["employee_id"] != self.employee.employee_id:
            # Same message whether the request does not exist or belongs to someone else.
            raise ToolError("I couldn't find that request among your leave requests.", "not_found")
        if req["status"] not in ("pending", "approved"):
            raise ToolError(f"This request is already {req['status']} and cannot be cancelled.")
        if not req["start_date"] > self.today.isoformat():
            raise ToolError(f"This request started on {req['start_date']}. Only requests that start after today "
                            f"({self.today.isoformat()}) can be cancelled.")
        return {k: req[k] for k in ("request_id", "leave_type", "start_date", "end_date", "working_days", "status")}

    def cancel_leave(self, request_id: str | None = None) -> ToolRecord:
        args = {"request_id": request_id}

        def fn():
            req = repo.get_request(request_id) if isinstance(request_id, str) else None
            return "pending_confirmation", {"proposal": self._validate_cancel(request_id, req)}

        return self.run("cancel_leave", args, fn)

    # ---- execution after confirmation -------------------------------------------------------

    def execute_proposal(self, proposal: dict) -> ToolRecord:
        name, args = proposal["name"], proposal["args"]
        if proposal.get("employee_id") != self.employee.employee_id:
            raise PermissionError("proposal belongs to another employee")

        if name == "apply_leave":
            def fn():
                checked: dict = {}

                def recheck(conn):
                    checked.update(self._validate_apply(args["leave_type"], args["start_date"], args["end_date"], conn))

                try:
                    request_id = repo.create_request_and_debit(
                        self.employee.employee_id, args["leave_type"], args["start_date"], args["end_date"],
                        self._working_days_for(args), recheck,
                    )
                except WriteConflict as exc:
                    raise ToolError(str(exc)) from None
                return "success", {"request_id": request_id, "status": "pending", **checked}

            return self.run("apply_leave", args, fn)

        if name == "cancel_leave":
            def fn():
                def recheck(conn, req):
                    self._validate_cancel(args["request_id"], req)

                req = repo.cancel_request_and_credit(args["request_id"], recheck)
                return "success", {"request_id": req["request_id"], "status": "cancelled",
                                   "working_days_returned": req["working_days"], "leave_type": req["leave_type"],
                                   "start_date": req["start_date"], "end_date": req["end_date"]}

            return self.run("cancel_leave", args, fn)
        raise ValueError(f"unknown proposal {name}")

    def _working_days_for(self, args: dict) -> int:
        start, end = date.fromisoformat(args["start_date"]), date.fromisoformat(args["end_date"])
        return count_working_days(start, end, set(self.holidays_between(start, end)))
