"""MCP server: use the Veltrix PeopleOps API from your own MCP client (Claude Desktop, Cursor, VS Code, agents).

Transport: Streamable HTTP at /mcp/ (mounted in the FastAPI app).
Auth: "Authorization: Bearer <personal token>" — create one in Settings → Integrations (POST /me/mcp-token).
Every tool runs as the token's employee through the same permission-checked code as the chat:
document eligibility, leave-data access, bulk limits, audit log and PII masking all apply.
Writes (apply/cancel leave) only happen through `ask_hr_assistant`, which keeps the confirmation step.
"""

from __future__ import annotations

import os
import uuid
from datetime import date

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from app.config import now, today
from app.data import repositories as repo
from app.data import state
from app.data.repositories import Employee
from app.identity.tokens import verify_token
from app.ingestion.pipeline import corpus_ready, get_corpus
from app.observability.logging import get_logger
from app.observability.pii import mask_email, mask_for_user
from app.retrieval.eligibility import Requester, can_read, is_eligible, is_upcoming, region_matches
from app.retrieval.search import search
from app.tools.leave_tools import ToolContext
from app.tools.permissions import viewable_employees
from app.tools.working_days import applicable_calendar

log = get_logger(__name__)

INSTRUCTIONS = (
    "Veltrix PeopleOps HR assistant for the signed-in employee (identity comes from the bearer token). "
    "Use ask_hr_assistant for questions and for applying/cancelling leave (it asks the user to confirm writes; "
    "send the user's confirmation in the same session_id). Read tools return only data this employee may see."
)

mcp = MCPServer(name="veltrix-peopleops", title="Veltrix PeopleOps", instructions=INSTRUCTIONS, version="1.0.0")


class Unauthorized(ToolError):
    """Shown to the MCP client (ToolError messages are passed through; other errors are hidden)."""


def _employee(ctx: Context) -> Employee:
    headers = {k.lower(): v for k, v in (ctx.headers or {}).items()}
    auth = headers.get("authorization", "")
    employee_id = verify_token(auth[7:].strip()) if auth.lower().startswith("bearer ") else None
    employee = repo.get_employee(employee_id) if employee_id else None
    if employee is None:
        raise Unauthorized("Missing or invalid token. Create one in the web app: Settings → Integrations.")
    return employee


def _ctx(employee: Employee) -> ToolContext:
    if not corpus_ready():
        raise ToolError("The service is still starting (ingestion running). Try again shortly.")
    return ToolContext(employee, f"mcp-{uuid.uuid4().hex[:12]}", today(), get_corpus())


def _out(rec) -> dict:
    data = {"tool": rec.name, "status": rec.status}
    data.update(rec.result if rec.status != "error" else {"error": rec.error})
    return data


@mcp.tool(description="Who am I? The signed-in employee's profile (no phone; email masked) and today's date.")
def whoami(ctx: Context) -> dict:
    e = _employee(ctx)
    reports = [{"employee_id": r.employee_id, "name": r.full_name}
               for r in viewable_employees(e) if r.manager_id == e.employee_id]
    return {"employee_id": e.employee_id, "name": e.full_name, "email": mask_email(e.email), "role": e.role,
            "region": e.region, "level": e.level, "join_date": e.join_date, "manager_id": e.manager_id,
            "direct_reports": reports, "today": today().isoformat(), "now": now().isoformat(timespec="minutes")}


@mcp.tool(description="Ask the HR assistant anything about Veltrix HR policies, holidays or your leave. Returns the "
                      "same JSON as POST /chat (answer, route, citations, tool_calls, pending_confirmation). To "
                      "confirm a proposed leave action, call again with the same session_id and message 'yes'.")
async def ask_hr_assistant(message: str, ctx: Context, session_id: str | None = None) -> dict:
    from app.api.routes import get_agent  # local import: avoids a cycle at start-up

    e = _employee(ctx)
    if not corpus_ready():
        raise ToolError("The service is still starting (ingestion running). Try again shortly.")
    session_id = session_id or f"mcp-{uuid.uuid4()}"
    if not state.claim_session(session_id, e.employee_id):
        raise Unauthorized("This session_id belongs to another employee.")
    result = await get_agent().handle(e, session_id, message, str(uuid.uuid4()))
    return {"session_id": session_id, **result.to_dict()}


@mcp.tool(description="Current leave balance. employee_id defaults to you; managers may pass a direct report, "
                      "HR any one employee.")
def get_leave_balance(ctx: Context, employee_id: str | None = None, leave_type: str | None = None) -> dict:
    return _out(_ctx(_employee(ctx)).get_leave_balance(employee_id, leave_type))


@mcp.tool(description="Leave requests of one employee (default: you). status: pending | approved | cancelled.")
def list_leave_requests(ctx: Context, employee_id: str | None = None, status: str | None = None) -> dict:
    return _out(_ctx(_employee(ctx)).list_leave_requests(employee_id, status))


@mcp.tool(description="Managers only: pending/approved leave of your direct reports overlapping a date range "
                      "(YYYY-MM-DD).")
def get_team_leave(ctx: Context, start_date: str, end_date: str) -> dict:
    e = _employee(ctx)
    rec = _ctx(e).get_team_leave(start_date, end_date)
    out = _out(rec)
    visible = {x.full_name for x in viewable_employees(e)}
    for row in out.get("team_leave", []):
        row["full_name"] = mask_for_user(row.get("full_name", ""), visible)
    return out


@mcp.tool(description="Public and restricted holidays for your office in a year, from the applicable calendar.")
def list_holidays(ctx: Context, year: int | None = None) -> dict:
    e = _employee(ctx)
    corpus = get_corpus()
    year = year or today().year
    cal = applicable_calendar(corpus.docs, corpus.holidays, Requester(e.employee_id, e.role, e.region), year)
    if cal is None:
        return {"year": year, "calendar": None, "holidays": []}
    return {"year": year, "calendar": {"doc_id": cal.doc_id, "title": cal.title},
            "holidays": [{"date": h.date.isoformat(), "name": h.name, "kind": h.kind}
                         for h in sorted(corpus.holidays.get(cal.doc_id, []), key=lambda h: h.date)
                         if h.date.year == year]}


@mcp.tool(description="HR documents you may read for your region (in effect or upcoming). Restricted documents "
                      "for other roles are never listed.")
def list_documents(ctx: Context) -> dict:
    e = _employee(ctx)
    corpus = get_corpus()
    req, t = Requester(e.employee_id, e.role, e.region), today()
    docs = [{"doc_id": d.doc_id, "title": d.title, "doc_type": d.doc_type, "regions": list(d.regions),
             "effective_date": d.effective_date,
             "status": "in_effect" if is_eligible(d, req, t) else "upcoming" if is_upcoming(d, req, t) else "other"}
            for d in corpus.docs.values() if can_read(e.role, d.access_level) and region_matches(d, e.region)]
    return {"documents": sorted(docs, key=lambda d: (d["status"], d["title"]))}


@mcp.tool(description="Search the HR documents that apply to you (role, region, date). Returns cited passages "
                      "(doc_id + section). as_of (YYYY-MM-DD) searches documents in effect on a past date.")
def search_hr_documents(query: str, ctx: Context, as_of: str | None = None, limit: int = 5) -> dict:
    e = _employee(ctx)
    ref = date.fromisoformat(as_of) if as_of else today()
    hits, _upcoming = search(get_corpus().index, query, Requester(e.employee_id, e.role, e.region), ref,
                             k=max(1, min(int(limit), 8)), include_upcoming=False)
    return {"as_of": ref.isoformat(), "results": [
        {"doc_id": h.doc.doc_id, "title": h.doc.title, "section": h.chunk.locator,
         "effective_date": h.doc.effective_date, "text": h.chunk.text} for h in hits]}


def build_mcp_app():
    """Starlette app for mounting at /mcp. Host/origin checks guard against DNS rebinding."""
    hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["localhost:*", "127.0.0.1:*", "api:*", "testserver", *hosts],
        allowed_origins=["http://localhost:*", "http://127.0.0.1:*", *[f"http://{h}" for h in hosts]],
    )
    return mcp.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True,
                                   transport_security=security)
