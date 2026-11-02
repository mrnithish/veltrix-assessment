"""Endpoints for the web UI: login, profile, leave dashboard, team, holidays, documents, chat history.

These are additions; the graded contract (POST /chat with X-Employee-Id) is unchanged. They require a
login token (Authorization: Bearer ...) and apply the same access rules as the chat tools.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import app_tz, get_settings, now, today
from app.data import repositories as repo
from app.data import state
from app.data.repositories import Employee
from app.identity.tokens import check_password, issue_token, verify_token
from app.ingestion.pipeline import corpus_ready, get_corpus
from app.observability.logging import get_logger
from app.observability.pii import mask_email
from app.retrieval.eligibility import Requester, can_read, is_eligible, is_upcoming, region_matches
from app.retrieval.precedence import precedence_key
from app.tools.leave_tools import ToolContext
from app.tools.permissions import NOT_ALLOWED_MESSAGE
from app.tools.working_days import applicable_calendar

log = get_logger(__name__)
router = APIRouter()


class LoginBody(BaseModel):
    identifier: str
    password: str


def current_user(request: Request) -> Employee:
    auth = request.headers.get("Authorization", "")
    employee_id = verify_token(auth[7:].strip() if auth.lower().startswith("bearer ") else None)
    employee = repo.get_employee(employee_id) if employee_id else None
    if employee is None:
        raise HTTPException(status_code=401, detail="Please sign in again")
    return employee


def _service(join_date: str, on: date) -> str:
    try:
        joined = date.fromisoformat(join_date)
    except ValueError:
        return ""
    months = (on.year - joined.year) * 12 + (on.month - joined.month) - (1 if on.day < joined.day else 0)
    return f"{months // 12} years {months % 12} months"


def _profile(e: Employee) -> dict:
    reports = [x for x in repo.list_employees() if x.manager_id == e.employee_id] if e.role == "manager" else []
    t = today()
    return {
        "employee_id": e.employee_id,
        "full_name": e.full_name,  # the user's own name
        "email": mask_email(e.email),  # masked, never the phone
        "role": e.role,
        "region": e.region,
        "level": e.level,
        "join_date": e.join_date,
        "length_of_service": _service(e.join_date, t),
        "manager_id": e.manager_id,
        "direct_reports": [{"employee_id": r.employee_id, "full_name": r.full_name, "level": r.level}
                           for r in reports],
        "today": t.isoformat(),
        "now": now().isoformat(timespec="seconds"),
        "timezone": str(app_tz()),
    }


# ---- auth ---------------------------------------------------------------------------------------

@router.post("/auth/login")
def login(body: LoginBody):
    ident = body.identifier.strip()
    employee = repo.get_employee(ident.upper()) or next(
        (e for e in repo.list_employees() if e.email.lower() == ident.lower()), None)
    if employee is None or not check_password(body.password):
        log.info("login_failed")
        raise HTTPException(status_code=401, detail="Employee ID/email or password is incorrect")
    log.info("login_ok", employee_id=employee.employee_id)
    return {"token": issue_token(employee.employee_id), "profile": _profile(employee)}


@router.get("/auth/demo-accounts")
def demo_accounts():
    """Sign-in helper for the demo: ids, roles and regions only (no names, emails or phones)."""
    if not get_settings().dev_endpoints:
        raise HTTPException(status_code=404, detail="Not found")
    people = repo.list_employees()
    reports = {e.employee_id: sum(1 for x in people if x.manager_id == e.employee_id) for e in people}
    return [{"employee_id": e.employee_id, "role": e.role, "region": e.region, "level": e.level,
             "direct_reports": reports[e.employee_id]} for e in people]


@router.get("/me")
def me(user: Employee = Depends(current_user)):
    return _profile(user)


# ---- leave dashboard ----------------------------------------------------------------------------

@router.get("/me/leave")
def my_leave(user: Employee = Depends(current_user)):
    t = today()
    requests = repo.list_requests(user.employee_id)
    for r in requests:
        r["cancellable"] = r["status"] in ("pending", "approved") and r["start_date"] > t.isoformat()
    return {"balances": {b["leave_type"]: b["balance_days"] for b in repo.get_balances(user.employee_id)},
            "requests": requests, "today": t.isoformat()}


@router.get("/me/team")
def my_team(start: str | None = None, end: str | None = None, user: Employee = Depends(current_user)):
    if user.role != "manager":
        raise HTTPException(status_code=403, detail="Team view is only available to managers")
    t = today()
    start = start or t.isoformat()
    end = end or (t + timedelta(days=30)).isoformat()
    if not corpus_ready():
        raise HTTPException(status_code=503, detail="Service is starting")
    ctx = ToolContext(user, "ui-team", t, get_corpus())
    rec = ctx.get_team_leave(start, end)  # same tool, same permission check, audited
    if rec.status == "error":
        raise HTTPException(status_code=400, detail=rec.error)
    reports = [{"employee_id": r.employee_id, "full_name": r.full_name, "level": r.level, "region": r.region}
               for r in repo.list_employees() if r.manager_id == user.employee_id]
    return {"start_date": start, "end_date": end, "team": reports, "leave": rec.result["team_leave"]}


@router.get("/me/team/{employee_id}/leave")
def team_member_leave(employee_id: str, user: Employee = Depends(current_user)):
    """One direct report at a time (no bulk views), through the permission-checked tools."""
    if not corpus_ready():
        raise HTTPException(status_code=503, detail="Service is starting")
    ctx = ToolContext(user, "ui-team-member", today(), get_corpus())
    bal = ctx.get_leave_balance(employee_id)
    if bal.status == "error":
        raise HTTPException(status_code=403, detail=NOT_ALLOWED_MESSAGE)
    reqs = ctx.list_leave_requests(employee_id)
    return {"employee_id": employee_id, "balances": bal.result["balances"], "requests": reqs.result["requests"]}


# ---- holidays & documents -----------------------------------------------------------------------

@router.get("/me/holidays")
def my_holidays(year: int | None = None, user: Employee = Depends(current_user)):
    if not corpus_ready():
        raise HTTPException(status_code=503, detail="Service is starting")
    corpus = get_corpus()
    year = year or today().year
    req = Requester(user.employee_id, user.role, user.region)
    cal = applicable_calendar(corpus.docs, corpus.holidays, req, year)
    if cal is None:
        return {"year": year, "calendar": None, "holidays": []}
    hols = sorted(corpus.holidays.get(cal.doc_id, []), key=lambda h: h.date)
    return {
        "year": year,
        "calendar": {"doc_id": cal.doc_id, "title": cal.title, "effective_date": cal.effective_date},
        "holidays": [{"date": h.date.isoformat(), "weekday": h.date.strftime("%A"), "name": h.name, "kind": h.kind}
                     for h in hols if h.date.year == year],
    }


@router.get("/me/documents")
def my_documents(user: Employee = Depends(current_user)):
    """Documents this user may read for their region. Restricted documents are never listed."""
    if not corpus_ready():
        raise HTTPException(status_code=503, detail="Service is starting")
    corpus = get_corpus()
    t = today()
    req = Requester(user.employee_id, user.role, user.region)
    sections: dict[str, list[str]] = {}
    for c in corpus.chunks:
        if c.locator not in sections.setdefault(c.doc_id, []):
            sections[c.doc_id].append(c.locator)
    out = []
    for d in corpus.docs.values():
        if not can_read(user.role, d.access_level) or not region_matches(d, user.region):
            continue
        status = "in_effect" if is_eligible(d, req, t) else ("upcoming" if is_upcoming(d, req, t) else "other")
        authority, scope, _ = precedence_key(d)
        out.append({"doc_id": d.doc_id, "title": d.title, "doc_type": d.doc_type, "regions": list(d.regions),
                    "effective_date": d.effective_date, "access_level": d.access_level, "status": status,
                    "authoritative": bool(authority), "region_specific": bool(scope),
                    "sections": sections.get(d.doc_id, [])})
    out.sort(key=lambda x: (x["status"] != "in_effect", x["doc_type"], x["title"]))
    return {"today": t.isoformat(), "documents": out}


# ---- chat history -------------------------------------------------------------------------------

@router.get("/sessions")
def list_my_sessions(user: Employee = Depends(current_user)):
    return [{**s, "title": (s.get("title") or "New conversation")[:80]} for s in state.list_sessions(user.employee_id)]


@router.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str, user: Employee = Depends(current_user)):
    if state.session_owner(session_id) != user.employee_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"session_id": session_id, "messages": state.session_messages(session_id),
            "pending_proposal": state.get_proposal(session_id) is not None}


@router.delete("/sessions/{session_id}")
def delete_my_session(session_id: str, user: Employee = Depends(current_user)):
    if state.session_owner(session_id) != user.employee_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    state.delete_session(session_id)
    return {"deleted": session_id}


# ---- MCP personal access token --------------------------------------------------------------------

MCP_TOKEN_TTL_S = 30 * 24 * 3600


@router.post("/me/mcp-token")
def create_mcp_token(request: Request, user: Employee = Depends(current_user)):
    """A 30-day personal token for your own MCP client, plus ready-to-paste client configurations."""
    token = issue_token(user.employee_id, MCP_TOKEN_TTL_S)
    base = str(request.base_url).rstrip("/")
    url = f"{base}/mcp/"
    header = f"Bearer {token}"
    log.info("mcp_token_issued", employee_id=user.employee_id)
    return {
        "token": token,
        "url": url,
        "expires_in_days": MCP_TOKEN_TTL_S // 86400,
        "tools": ["whoami", "ask_hr_assistant", "get_leave_balance", "list_leave_requests", "get_team_leave",
                  "list_holidays", "list_documents", "search_hr_documents"],
        "configs": {
            "claude_code": f'claude mcp add --transport http veltrix {url} --header "Authorization: {header}"',
            "cursor": {"mcpServers": {"veltrix": {"url": url, "headers": {"Authorization": header}}}},
            "vscode": {"servers": {"veltrix": {"type": "http", "url": url, "headers": {"Authorization": header}}}},
            "claude_desktop": {"mcpServers": {"veltrix": {
                "command": "npx", "args": ["-y", "mcp-remote", url, "--header", f"Authorization: {header}"]}}},
        },
    }
