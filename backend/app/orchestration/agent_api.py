"""The functions an agent can call during one turn (shared by Code Mode and tool-calling mode).

Each function is bound to the server-side ToolContext, so identity and permissions never come
from the model. Results are JSON-safe dicts with personal data minimised (no emails/phones).
"""

from __future__ import annotations

from datetime import date

from app.orchestration.dates import resolve_dates
from app.retrieval.search import Hit, search
from app.tools.leave_tools import ToolContext, ToolRecord
from app.tools.permissions import viewable_employees
from app.tools.working_days import count_working_days


def _record_out(rec: ToolRecord) -> dict:
    if rec.status == "error":
        return {"ok": False, "error": rec.error}
    return {"ok": True, "status": rec.status, **rec.result}


class AgentAPI:
    def __init__(self, ctx: ToolContext, trace=None, default_as_of: date | None = None):
        self.ctx = ctx
        self.trace = trace
        # A past date the user asked about (TASK 5): used when the model forgets to pass as_of.
        self.default_as_of = default_as_of
        self.hits: list[Hit] = []  # current passages, in the order they were found
        self.upcoming: list[Hit] = []
        self.searches: list[dict] = []
        self.structured_sources: list[tuple[str, str]] = []  # (doc_id, locator) used via get_holidays
        self.employee_lookups: list[dict] = []
        # Structured helper outputs (holidays, working-day counts) always reach the answer step,
        # even if the model's code does not keep them in `result`.
        self.helper_results: list[dict] = []
        self.profile_used = False

    # ---- contract tools -------------------------------------------------------------------

    def get_leave_balance(self, employee_id=None, leave_type=None):
        return _record_out(self.ctx.get_leave_balance(employee_id, leave_type))

    def list_leave_requests(self, employee_id=None, status=None):
        return _record_out(self.ctx.list_leave_requests(employee_id, status))

    def get_team_leave(self, start_date=None, end_date=None):
        return _record_out(self.ctx.get_team_leave(start_date, end_date))

    def apply_leave(self, leave_type=None, start_date=None, end_date=None):
        return _record_out(self.ctx.apply_leave(leave_type, start_date, end_date))

    def cancel_leave(self, request_id=None):
        return _record_out(self.ctx.cancel_leave(request_id))

    # ---- helpers ----------------------------------------------------------------------------

    def search_policies(self, query="", as_of=None):
        today = self.ctx.today
        ref = self.default_as_of or today
        if as_of:
            try:
                ref = date.fromisoformat(str(as_of)[:10])
            except ValueError:
                return {"ok": False, "error": "as_of must be YYYY-MM-DD"}
        if not isinstance(query, str) or not query.strip():
            return {"ok": False, "error": "query must be a non-empty string"}
        current, upcoming = search(
            self.ctx.corpus.index, query.strip(), self.ctx.requester, ref, k=8,
            include_upcoming=(ref >= today),
        )
        known = {h.chunk.chunk_id for h in self.hits}
        for h in current:
            if h.chunk.chunk_id not in known:
                self.hits.append(h)
                known.add(h.chunk.chunk_id)
        known_up = {h.chunk.chunk_id for h in self.upcoming}
        for h in upcoming:
            if h.chunk.chunk_id not in known_up:
                self.upcoming.append(h)
                known_up.add(h.chunk.chunk_id)
        self.searches.append({"query": query, "as_of": ref.isoformat(),
                              "hits": [h.chunk.chunk_id for h in current],
                              "upcoming": [h.chunk.chunk_id for h in upcoming]})
        return [{"ref": h.chunk.chunk_id, "doc_id": h.doc.doc_id, "section": h.chunk.locator} for h in current]

    def _dates(self, start_date, end_date):
        try:
            return date.fromisoformat(str(start_date)), date.fromisoformat(str(end_date))
        except ValueError:
            return None, None

    def get_holidays(self, start_date=None, end_date=None):
        start, end = self._dates(start_date, end_date)
        if not start or not end or end < start:
            return {"ok": False, "error": "start_date and end_date must be YYYY-MM-DD with start <= end"}
        hols = self.ctx.holidays_between(start, end)
        for _d, (_name, doc_id) in hols.items():
            loc = self._calendar_locator(doc_id)
            if (doc_id, loc) not in self.structured_sources:
                self.structured_sources.append((doc_id, loc))
        out = {"ok": True, "holidays": [{"date": d.isoformat(), "weekday": d.strftime("%A"), "name": n}
                                        for d, (n, _doc) in sorted(hols.items())]}
        self.helper_results.append({"fn": "get_holidays", "start_date": start.isoformat(),
                                    "end_date": end.isoformat(), **out})
        return out

    def _calendar_locator(self, doc_id: str) -> str:
        for c in self.ctx.corpus.chunks:
            if c.doc_id == doc_id and "|" in c.text:
                return c.locator
        return next((c.locator for c in self.ctx.corpus.chunks if c.doc_id == doc_id), "p. 1")

    def count_working_days(self, start_date=None, end_date=None):
        start, end = self._dates(start_date, end_date)
        if not start or not end:
            return {"ok": False, "error": "dates must be YYYY-MM-DD"}
        hols = self.ctx.holidays_between(start, end)
        out = {"ok": True, "working_days": count_working_days(start, end, set(hols)),
               "public_holidays": [{"date": d.isoformat(), "name": n} for d, (n, _doc) in sorted(hols.items())]}
        self.helper_results.append({"fn": "count_working_days", "start_date": start.isoformat(),
                                    "end_date": end.isoformat(), **out})
        return out

    def resolve_dates(self, phrase=""):
        return resolve_dates(str(phrase), self.ctx.today)

    def get_my_profile(self):
        """The signed-in requester's own profile (no email or phone)."""
        self.profile_used = True
        e = self.ctx.employee
        reports = [{"employee_id": r.employee_id, "name": r.full_name, "level": r.level}
                   for r in viewable_employees(e) if r.manager_id == e.employee_id]
        return {"ok": True, "employee_id": e.employee_id, "name": e.full_name, "role": e.role, "region": e.region,
                "level": e.level, "join_date": e.join_date, "manager_id": e.manager_id, "direct_reports": reports}

    def find_employee(self, name=""):
        q = str(name or "").strip().lower()
        if len(q) < 2:
            return {"ok": True, "matches": []}
        matches = [
            {"employee_id": e.employee_id, "name": e.full_name}
            for e in viewable_employees(self.ctx.employee)
            if q in e.full_name.lower() or q == e.employee_id.lower()
        ][:5]
        self.employee_lookups.append({"matches": [m["employee_id"] for m in matches]})
        return {"ok": True, "matches": matches}

    def functions(self) -> dict:
        names = ["get_leave_balance", "list_leave_requests", "get_team_leave", "apply_leave", "cancel_leave",
                 "search_policies", "get_holidays", "count_working_days", "resolve_dates", "find_employee",
                 "get_my_profile"]
        return {n: getattr(self, n) for n in names}

    def visible_names(self) -> set[str]:
        """Names the requester is allowed to see in this answer."""
        names = {self.ctx.employee.full_name}
        for e in viewable_employees(self.ctx.employee):
            if self.ctx.employee.role != "hr" or any(
                e.employee_id in (r.result.get("employee_id"), r.args.get("employee_id"))
                for r in self.ctx.records
            ) or any(e.employee_id in lk["matches"] for lk in self.employee_lookups):
                names.add(e.full_name)
        return names
