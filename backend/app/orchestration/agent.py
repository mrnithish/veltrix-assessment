"""Chat orchestration.

Per message:
  1. pending proposal?  confirmation -> execute the write; anything else -> discard and continue
  2. plan              LLM (0 corpus tokens) -> clarify / refuse / Python code (Code Mode) or tool calls
  3. gather            run the code in the sandbox; tools enforce permissions with the header identity
  4. extract           LLM lists candidate values per rule from <= 3,000 tokens of eligible passages
  5. resolve           Python applies precedence (authority > scope > recency), conflicts, upcoming changes
  6. compose           LLM writes the answer from resolved facts + tool results
  7. route & mask      deterministic route, citations from resolved facts, PII masking, trace + audit
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.config import get_settings
from app.config import now as app_now
from app.config import today as app_today
from app.data import repositories as repo
from app.data import state
from app.data.repositories import Employee
from app.ingestion.pipeline import get_corpus
from app.llm.base import LLMError, call_llm, parse_json_object
from app.llm.tokens import count_tokens
from app.observability import metrics
from app.observability.logging import get_logger
from app.observability.pii import mask_for_user
from app.observability.tracing import RequestTrace
from app.orchestration import prompts
from app.orchestration.agent_api import AgentAPI
from app.orchestration.codemode.sandbox import run_code
from app.orchestration.dates import calendar_lines, past_reference_date
from app.orchestration.events import NULL_SINK, instrument
from app.retrieval.budget import EvidencePack, pack
from app.retrieval.eligibility import eligibility_stats
from app.retrieval.precedence import (
    Candidate,
    Resolution,
    drop_redundant_low_authority,
    normalize_value,
    resolve_rule,
    rule_matches_passage,
)
from app.tools.leave_tools import CONTRACT_TOOLS, ToolContext
from app.tools.permissions import BULK_MESSAGE, NOT_ALLOWED_MESSAGE

log = get_logger(__name__)

REQUEST_DEADLINE_S = 26.0  # the route's hard limit is 29 s; finish (and save the trace) before it

REFUSALS = {
    "off_topic": "I can only help with Veltrix HR topics: HR policies, holidays and benefits, and your leave "
                 "(balances, requests, applying for or cancelling leave). Please ask me something in that area.",
    "manipulation": "I can't help with that. I can answer questions about Veltrix HR policies and help you "
                    "with your leave.",
    "bulk": BULK_MESSAGE,
    "not_permitted": NOT_ALLOWED_MESSAGE,
}
NO_ANSWER = ("The HR documents available to me don't cover this question, so I can't answer it reliably. "
             "Please contact the HR team for help.")
UNAVAILABLE = "Sorry, I couldn't process that request right now. Please try again, or contact the HR team."
LEAVE_TYPE_QUESTION = "Should this be annual leave or sick leave?"
_CANCEL_INTENT = re.compile(r"\bcancel\b", re.IGNORECASE)
OUT_OF_SCOPE_LEAVE = ("I can only help with whole-day leave in 2026. Half-day leave, leave in other years and "
                      "approving or rejecting leave requests are outside what I can do here.")
_OUT_OF_SCOPE_LEAVE = re.compile(
    r"\bhalf[- ]?(?:a[- ])?day\b|\b(?:approve|reject|decline)\b.{0,40}\b(?:leave|request)", re.IGNORECASE)
LEAVE_DETAILS_QUESTION = ("To set this up, please tell me the leave type (annual or sick) and the exact dates "
                          "(start and end).")
_LEAVE_ACTION = re.compile(
    r"\b(book|apply|take|request|need|want|cancel)\b.*\b(leave|off|holiday|vacation|pto|sick)\b|\bday off\b", re.I)

_CONFIRM_STRONG = {"yes", "y", "yep", "yeah", "yup", "sure", "ok", "okay", "confirm", "confirmed", "proceed",
                   "go", "correct", "submit", "affirmative"}
_CONFIRM_WEAK = {"please", "ahead", "do", "it", "thanks", "thank", "you", "that's", "thats", "right", "fine",
                 "sounds", "good", "great", "perfect", "i", "the", "request", "leave", "cancellation", "book",
                 "apply", "cancel"}
_NEGATIONS = {"no", "not", "don't", "dont", "wait", "instead", "change", "but", "stop", "nope", "never"}
_ANNUAL_CUE = re.compile(r"\b(annual|vacation|pto|paid time off|holiday leave|earned leave)\b", re.IGNORECASE)
_SICK_CUE = re.compile(r"\b(sick|ill|unwell|medical|doctor|fever|flu|hospital|illness)\b", re.IGNORECASE)


def is_confirmation(message: str) -> bool:
    words = re.findall(r"[a-z']+", message.lower())
    if not words or len(words) > 8 or re.search(r"\d", message):
        return False
    if any(w in _NEGATIONS for w in words):
        return False
    if not any(w in _CONFIRM_STRONG for w in words):
        return False
    return all(w in _CONFIRM_STRONG or w in _CONFIRM_WEAK for w in words)


def leave_type_sources(message: str, history: list[dict]) -> list[str]:
    """Where the user may have stated the leave type for THIS request.

    The current message, plus the previous user message only when the assistant's last reply was a
    question (e.g. "Which dates?"), i.e. the user is still completing the same request. Older questions
    in the chat ("how many annual days do I have?") must not count as choosing a leave type.
    """
    texts = [message]
    last_assistant = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
    if last_assistant.rstrip().endswith("?"):
        prev_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), None)
        if prev_user:
            texts.append(prev_user)
    return texts


def has_leave_type_cue(texts: list[str], leave_type: str) -> bool:
    rx = _ANNUAL_CUE if leave_type == "annual" else _SICK_CUE
    return any(rx.search(t or "") for t in texts)


@dataclass
class ChatResult:
    request_id: str
    answer: str
    route: str
    citations: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    pending_confirmation: bool = False

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "answer": self.answer,
            "route": self.route,
            "citations": self.citations,
            "tool_calls": self.tool_calls,
            "pending_confirmation": self.pending_confirmation,
        }


@dataclass
class Gathered:
    kind: str  # data | clarify | refuse | respond | error
    message: str = ""
    refuse_reason: str = ""
    result: Any = None
    error: str | None = None


@dataclass
class Turn:
    employee: Employee
    session_id: str
    message: str
    request_id: str
    today: date
    ctx: ToolContext
    api: AgentAPI
    trace: RequestTrace
    history: list[dict]
    deadline: float
    events: Any = None  # EventSink for /chat/stream, NullSink otherwise
    replaced_proposal: dict | None = None  # proposal discarded by this message (e.g. a change of dates)

    def timeout(self) -> float:
        """Time budget for the next LLM call; raises when the request deadline is too close."""
        remaining = self.deadline - time.monotonic() - 0.5
        if remaining < 2.0:
            raise LLMError("request deadline reached before the next LLM call")
        return min(get_settings().llm_timeout_s, remaining)


class Agent:
    def __init__(self, llm, mode: str | None = None):
        self.llm = llm
        self.mode = (mode or get_settings().agent_mode).lower()

    # ------------------------------------------------------------------ entry point
    async def handle(self, employee: Employee, session_id: str, message: str, request_id: str,
                     events=None) -> ChatResult:
        sink = events or NULL_SINK
        today = app_today()
        corpus = get_corpus()
        trace = RequestTrace(request_id, session_id, employee.employee_id)
        trace.events = sink
        ctx = ToolContext(employee, request_id, today, corpus)
        api = AgentAPI(ctx, trace, past_reference_date(message, today))
        turn = Turn(employee, session_id, message, request_id, today, ctx, api, trace,
                    state.recent_messages(session_id), time.monotonic() + REQUEST_DEADLINE_S, sink)
        sink.emit("start", request_id=request_id, mode=self.mode, provider=self.llm.provider, model=self.llm.model)
        if api.default_as_of:
            sink.emit("note", text=f"Question is about a past date: documents in effect on "
                                   f"{api.default_as_of.isoformat()} are used.")
        trace.set("agent_mode", self.mode)
        trace.set("llm", {"provider": self.llm.provider, "model": self.llm.model})
        trace.set("today", today.isoformat())
        trace.set("requester", {"employee_id": employee.employee_id, "role": employee.role,
                                "region": employee.region})
        trace.set("eligibility", eligibility_stats(corpus.docs, ctx.requester, today))
        t0 = time.perf_counter()
        try:
            with trace.step("chat.handle", mode=self.mode):
                result = await self._handle(turn)
        except LLMError as exc:
            log.error("chat_llm_unavailable", error=str(exc)[:300])
            result = ChatResult(request_id, UNAVAILABLE, "no_answer")
            trace.set("error", str(exc)[:500])
        except Exception as exc:  # never lose the trace of a failed request
            log.exception("chat_internal_error")
            result = ChatResult(request_id, UNAVAILABLE, "no_answer")
            trace.set("error", f"{type(exc).__name__}: {str(exc)[:400]}")
        result.answer = mask_for_user(result.answer, api.visible_names())
        metrics.CHAT_REQUESTS.labels(result.route).inc()
        metrics.CHAT_LATENCY.observe(time.perf_counter() - t0)
        state.add_message(session_id, "user", message, request_id)
        state.add_message(session_id, "assistant", result.answer, request_id)
        trace.set("response", result.to_dict())
        sink.emit("final", response=result.to_dict(), total_ms=round((time.perf_counter() - t0) * 1000))
        trace.set("all_tool_records", [
            {"name": r.name, "args": r.public()["args"], "status": r.status, "error_kind": r.error_kind,
             "duration_ms": r.duration_ms} for r in ctx.records])
        state.save_trace(request_id, session_id, employee.employee_id, result.route, trace.to_dict())
        log.info("chat_response", route=result.route, tools=[t["name"] for t in result.tool_calls],
                 citations=[c["doc_id"] for c in result.citations], pending=result.pending_confirmation,
                 llm_calls=len(trace.llm_calls), total_ms=round((time.perf_counter() - t0) * 1000, 1))
        return result

    async def _handle(self, turn: Turn) -> ChatResult:
        pending = state.get_proposal(turn.session_id)
        if pending:
            state.clear_proposal(turn.session_id)  # at most one proposal; any message consumes it
            confirmed = is_confirmation(turn.message)
            turn.trace.set("pending_proposal", {"name": pending["name"], "confirmed": confirmed})
            if confirmed:
                turn.events.emit("phase", name="confirm", label=f"Confirmed — running {pending['name']}")
                with turn.trace.step("proposal.execute", tool=pending["name"]):
                    result = self._execute(turn, pending)
                rec = turn.ctx.records[-1]
                turn.events.emit("call_done", fn=rec.name, ok=rec.status == "success",
                                 summary=rec.error or f"{rec.status}: {rec.result.get('request_id', '')}",
                                 ms=rec.duration_ms)
                return result
            turn.events.emit("note", text=f"Previous {pending['name']} proposal discarded (not a confirmation).")
            turn.replaced_proposal = pending
        if _OUT_OF_SCOPE_LEAVE.search(turn.message):
            turn.trace.set("scope_guard", "half-day leave or leave approval: out of scope (TASK 3)")
            turn.events.emit("note", text="Half-day leave and leave approval are out of scope.")
            return ChatResult(turn.request_id, OUT_OF_SCOPE_LEAVE, "refuse")
        turn.events.emit("phase", name="plan",
                         label="Writing a plan as code" if self.mode != "tools" else "Planning tool calls")
        with turn.trace.step("plan", mode=self.mode):
            gathered = await (self._gather_tools(turn) if self.mode == "tools" else self._gather_codemode(turn))
        with turn.trace.step("respond"):
            return await self._respond(turn, gathered)

    # ------------------------------------------------------------------ confirmation
    def _execute(self, turn: Turn, proposal: dict) -> ChatResult:
        rec = turn.ctx.execute_proposal(proposal)
        a = rec.args
        if rec.status == "success":
            r = rec.result
            if rec.name == "apply_leave":
                answer = (f"Done. Your {a['leave_type']} leave request from {a['start_date']} to {a['end_date']} "
                          f"({r['working_days']} working day{'s' if r['working_days'] != 1 else ''}) has been "
                          f"submitted with status pending. Request ID: {r['request_id']}. Your {a['leave_type']} "
                          f"balance is now {r['balance_after']:g} days.")
            else:
                answer = (f"Done. Request {r['request_id']} ({r['leave_type']} leave, {r['start_date']} to "
                          f"{r['end_date']}) is cancelled and {r['working_days_returned']} working day(s) were "
                          f"returned to your {r['leave_type']} balance.")
        else:
            verb = "submit this leave request" if rec.name == "apply_leave" else "cancel this request"
            answer = f"I couldn't {verb}: {rec.error}"
        return ChatResult(turn.request_id, answer, "tool", [], [rec.public()], False)

    # ------------------------------------------------------------------ planning (Code Mode)
    def _system_vars(self, turn: Turn) -> dict:
        e = turn.employee
        current = app_now()
        reports = [r.employee_id for r in repo.list_employees() if r.manager_id == e.employee_id]
        return dict(employee_id=e.employee_id, role=e.role, region=e.region, level=e.level, join_date=e.join_date,
                    service=service_length(e.join_date, turn.today), manager=e.manager_id or "none",
                    reports=", ".join(reports) if reports else "none", today=turn.today.isoformat(),
                    weekday=turn.today.strftime("%A"), time=current.strftime("%H:%M"),
                    timezone=current.tzname() or "UTC", calendar=calendar_lines(turn.today))

    def _history_messages(self, turn: Turn) -> list[dict]:
        out = []
        for m in turn.history[-6:]:
            role = "assistant" if m["role"] == "assistant" else "user"
            out.append({"role": role, "content": m["content"][:1500]})
        return out

    async def _gather_codemode(self, turn: Turn) -> Gathered:
        system = prompts.PLANNER_SYSTEM.format(api_spec=prompts.API_SPEC, **self._system_vars(turn))
        messages = [{"role": "system", "content": system}, *self._history_messages(turn),
                    {"role": "user", "content": turn.message}]
        last_error = None
        for attempt in range(2):
            resp = await call_llm(self.llm, messages, purpose="plan", corpus_tokens=0, trace=turn.trace,
                                  json_mode=True, max_tokens=1000, timeout=turn.timeout())
            try:
                plan = parse_json_object(resp.text)
            except ValueError:
                plan = {}
                fence = re.search(r"```(?:python)?\s*(.*?)```", resp.text or "", re.DOTALL)
                if fence:
                    plan = {"action": "code", "code": fence.group(1)}
            action = str(plan.get("action", "")).lower()
            turn.trace.set(f"plan_{attempt}", {"action": action, "code": plan.get("code"),
                                                "refuse_reason": plan.get("refuse_reason")})
            turn.events.emit("plan", attempt=attempt, action=action or "invalid",
                             code=plan.get("code") if isinstance(plan.get("code"), str) else None,
                             refuse_reason=plan.get("refuse_reason"))
            if action in ("clarify", "refuse", "respond"):
                return Gathered(action, message=str(plan.get("message") or ""),
                                refuse_reason=str(plan.get("refuse_reason") or ""))
            if action == "code" and isinstance(plan.get("code"), str):
                code = plan["code"]
                turn.events.emit("phase", name="run", label="Running the code in the sandbox")
                with turn.trace.step("codemode.execute", attempt=attempt) as st:
                    sr = await asyncio.to_thread(
                        run_code, code, instrument(turn.api.functions(), turn.events),
                        {"me": {"employee_id": turn.employee.employee_id, "role": turn.employee.role,
                                "region": turn.employee.region, "join_date": turn.employee.join_date,
                                "level": turn.employee.level, "manager_id": turn.employee.manager_id,
                                "direct_reports": [r.employee_id for r in repo.list_employees()
                                                   if r.manager_id == turn.employee.employee_id]},
                         "today": turn.today.isoformat()},
                    )
                    st.update({"code": code, "ok": sr.ok, "error": sr.error, "calls": sr.calls,
                               "stdout": sr.stdout[:2000], "sandbox_ms": sr.duration_ms})
                turn.events.emit("sandbox", ok=sr.ok, error=sr.error, ms=sr.duration_ms, calls=len(sr.calls))
                if sr.ok:
                    return Gathered("data", result=sr.result)
                last_error = sr.error
                feedback = f"Your code failed: {sr.error}. Reply with corrected JSON."
            else:
                last_error = "invalid planner output"
                feedback = "Reply with exactly one JSON object in the specified format."
            if time.monotonic() > turn.deadline - 8:
                break
            messages += [{"role": "assistant", "content": resp.text or ""}, {"role": "user", "content": feedback}]
        return Gathered("error", error=last_error)

    # ------------------------------------------------------------------ planning (tool-calling fallback)
    async def _gather_tools(self, turn: Turn) -> Gathered:
        from app.orchestration.tool_schemas import TOOL_SCHEMAS

        system = prompts.TOOLS_SYSTEM.format(**self._system_vars(turn))
        messages = [{"role": "system", "content": system}, *self._history_messages(turn),
                    {"role": "user", "content": turn.message}]
        fns = instrument(turn.api.functions(), turn.events)
        corpus_in_context = 0  # doc ids / section headings returned to the model are corpus-derived
        for _round in range(5):
            resp = await call_llm(self.llm, messages, purpose="plan_tools", corpus_tokens=corpus_in_context,
                                  trace=turn.trace,
                                  tools=TOOL_SCHEMAS, max_tokens=1200, timeout=turn.timeout())
            if not resp.tool_calls:
                return Gathered("data")
            messages.append({"role": "assistant", "content": resp.text or "", "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}} for tc in resp.tool_calls]})
            for tc in resp.tool_calls:
                if tc.name == "refuse":
                    return Gathered("refuse", refuse_reason=str(tc.arguments.get("reason", "off_topic")))
                if tc.name == "ask_clarification":
                    return Gathered("clarify", message=str(tc.arguments.get("message", "")))
                fn = fns.get(tc.name)
                try:
                    out = fn(**tc.arguments) if fn else {"ok": False, "error": f"unknown function {tc.name}"}
                except TypeError as exc:
                    out = {"ok": False, "error": f"bad arguments: {exc}"}
                content = json.dumps(out, default=str)
                if tc.name == "search_policies":
                    corpus_in_context += count_tokens(content)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
            if time.monotonic() > turn.deadline - 10:
                break
        return Gathered("data")

    # ------------------------------------------------------------------ response
    async def _respond(self, turn: Turn, g: Gathered) -> ChatResult:
        rid = turn.request_id
        records = [r for r in turn.ctx.records if r.name in CONTRACT_TOOLS]
        result = g.result if isinstance(g.result, dict) else {}

        if g.kind == "refuse":
            return ChatResult(rid, REFUSALS.get(g.refuse_reason, REFUSALS["off_topic"]), "refuse")
        for r in records:
            if r.error_kind == "bulk":
                return ChatResult(rid, BULK_MESSAGE, "refuse")
            if r.error_kind == "permission":
                return ChatResult(rid, r.error or NOT_ALLOWED_MESSAGE, "refuse")
        lookups = turn.api.employee_lookups
        if result.get("cannot_share_employee") and lookups and not lookups[-1]["matches"]:
            return ChatResult(rid, NOT_ALLOWED_MESSAGE, "refuse")
        if g.kind == "clarify":
            return ChatResult(rid, g.message or "Could you give me a few more details?", "clarify")
        if g.kind == "respond":
            return ChatResult(rid, g.message or "Hello! How can I help with HR or leave today?", "clarify")
        if g.kind == "error":
            return ChatResult(rid, "I couldn't work that out. Could you rephrase your question?", "clarify")
        if isinstance(result.get("clarify"), str) and result["clarify"].strip():
            return ChatResult(rid, result["clarify"].strip(), "clarify")

        # ---- cancel intent the plan did not complete (it only listed requests): finish it in code
        if (_CANCEL_INTENT.search(turn.message) and not any(r.name in ("apply_leave", "cancel_leave") for r in records)
                and any(r.name == "list_leave_requests" and r.status == "success" for r in records)):
            outcome = self._complete_cancel(turn)
            if outcome is not None:
                return outcome
            records = [r for r in turn.ctx.records if r.name in CONTRACT_TOOLS]

        # ---- write actions: propose (or reject) without asking the LLM to phrase it
        writes = [r for r in records if r.name in ("apply_leave", "cancel_leave")]
        if writes:
            last = writes[-1]
            public = [r.public() for r in records]
            if last.status == "pending_confirmation":
                p = last.result["proposal"]
                if last.name == "apply_leave":
                    prior = (turn.replaced_proposal or {}).get("args", {}).get("leave_type")
                    if prior != p["leave_type"] and not has_leave_type_cue(
                            leave_type_sources(turn.message, turn.history), p["leave_type"]):
                        turn.trace.set("leave_type_guard", "leave type not stated by user; asking")
                        turn.events.emit("note", text="Leave type was not stated — asking instead of assuming.")
                        return ChatResult(rid, LEAVE_TYPE_QUESTION, "clarify")
                    hol = p.get("public_holidays_in_range") or []
                    hol_txt = (" (excluding public holiday" + ("s" if len(hol) > 1 else "") + ": "
                               + ", ".join(f"{h['name']} on {h['date']}" for h in hol) + ")") if hol else ""
                    answer = (f"Please confirm: apply for {p['leave_type']} leave from {p['start_date']} to "
                              f"{p['end_date']}, which is {p['working_days']} working "
                              f"day{'s' if p['working_days'] != 1 else ''}{hol_txt}. Your {p['leave_type']} balance "
                              f"would go from {p['balance_before']:g} to {p['balance_after']:g} days. Reply 'yes' "
                              f"to confirm, or tell me what to change.")
                else:
                    answer = (f"Please confirm: cancel your {p['leave_type']} leave request from {p['start_date']} "
                              f"to {p['end_date']} ({p['working_days']} working days, currently {p['status']}, "
                              f"request ID {p['request_id']}). The days will be returned to your balance. "
                              f"Reply 'yes' to confirm.")
                state.set_proposal(turn.session_id, {"name": last.name, "args": {
                    k: v for k, v in last.args.items() if v is not None}, "employee_id": turn.employee.employee_id,
                    "summary": p})
                return ChatResult(rid, answer, "tool", [], public, True)
            if last.error_kind in ("past_date", "needs_detail"):  # TASK 8.4: ask, don't reject
                turn.events.emit("note", text="Date already passed or a detail is invalid — asking instead.")
                return ChatResult(rid, f"{last.error} Which dates would you like instead?"
                                  if last.error_kind == "past_date" else f"{last.error} Could you tell me which one?",
                                  "clarify")
            if last.error_kind == "out_of_scope":  # TASK 3: leave outside 2026 is out of scope
                return ChatResult(rid, OUT_OF_SCOPE_LEAVE, "refuse")
            verb = "apply for this leave" if last.name == "apply_leave" else "cancel this request"
            return ChatResult(rid, f"I can't {verb}: {last.error}", "tool", [], public, False)

        # ---- documents: extract -> resolve -> cite
        api = turn.api
        resolutions: list[Resolution] = []
        uncovered = ""
        evidence: EvidencePack | None = None
        if api.hits or api.upcoming:
            with turn.trace.step("budget.pack") as st:
                evidence = pack(api.hits, api.upcoming)
                st.update({"corpus_tokens": evidence.tokens, "items": [
                    {"ref": e.evidence_id, "chunk": e.hit.chunk.chunk_id, "tokens": e.tokens}
                    for e in evidence.items], "dropped": evidence.dropped})
            turn.trace.set("searches", api.searches)
            turn.events.emit("evidence", corpus_tokens=evidence.tokens, budget=3000, dropped=len(evidence.dropped),
                             items=[{"ref": e.evidence_id, "doc_id": e.hit.doc.doc_id, "section": e.hit.chunk.locator,
                                     "tokens": e.tokens, "upcoming": e.hit.upcoming} for e in evidence.items])
            if evidence.items:
                turn.events.emit("phase", name="extract", label="Reading the passages that apply to you")
                resolutions, uncovered, coverage = await self._extract_and_resolve(turn, evidence)
                turn.trace.set("coverage", coverage)
        citations = _citations(resolutions, api.structured_sources)
        turn.trace.set("resolutions", [r.to_trace() for r in resolutions])
        if resolutions:
            turn.events.emit("resolution", rules=[r.to_trace() for r in resolutions])

        has_tools = bool(records)
        has_docs = bool(citations)
        if not has_tools and not has_docs and api.profile_used:
            # Answered from the requester's own HR record (who am I / my manager / my team): no tool call or
            # document, so it uses the conversational route (see README assumptions).
            return ChatResult(rid, await self._compose(turn, [], "", result), "clarify")
        if not has_tools and not has_docs:
            if _LEAVE_ACTION.search(turn.message):  # a leave action the plan did not complete: ask, don't guess
                turn.trace.set("leave_action_guard", "leave action without a tool call; asking for details")
                turn.events.emit("note", text="Leave action without complete details — asking instead of guessing.")
                return ChatResult(rid, LEAVE_DETAILS_QUESTION, "clarify")
            return ChatResult(rid, NO_ANSWER, "no_answer")

        answer = await self._compose(turn, resolutions, uncovered, result)
        route = "hybrid" if (has_tools and has_docs) else ("rag" if has_docs else "tool")
        return ChatResult(rid, answer, route, citations, [r.public() for r in records], False)

    def _complete_cancel(self, turn: Turn) -> ChatResult | None:
        """One cancellable request matching the message -> propose cancelling it (via the tool, so the same
        checks apply); several -> ask which one. Returns None to continue with the normal flow."""
        today_iso = turn.today.isoformat()
        cancellable = [r for r in repo.list_requests(turn.employee.employee_id)
                       if r["status"] in ("pending", "approved") and r["start_date"] > today_iso]
        mentioned = mentioned_dates(turn.message, turn.today)
        if mentioned:
            cancellable = [r for r in cancellable if any(r["start_date"] <= d <= r["end_date"] for d in mentioned)]
        if len(cancellable) == 1:
            turn.trace.set("cancel_fallback", "plan listed requests only; proposing the single matching request")
            turn.ctx.cancel_leave(cancellable[0]["request_id"])
            return None
        if len(cancellable) > 1:
            options = "; ".join(f"{r['leave_type']} {r['start_date']} to {r['end_date']} ({r['status']})"
                                for r in cancellable)
            return ChatResult(turn.request_id, f"Which request should I cancel: {options}?", "clarify")
        return None

    async def _extract_and_resolve(self, turn: Turn, evidence: EvidencePack):
        prev_user = next((m["content"] for m in reversed(turn.history) if m["role"] == "user"), "")
        context = f"Previous user message (for context only): {prev_user[:400]}\n" if prev_user else ""
        ref_dates = sorted({s["as_of"] for s in turn.api.searches})
        user = (f"{context}Question: {turn.message}\n"
                f"Requester: {_requester_line(turn)}. "
                f"Reference date(s): {', '.join(ref_dates) or turn.today.isoformat()}.\n\n"
                f"Passages:\n{evidence.render()}")
        resp = await call_llm(self.llm, [{"role": "system", "content": prompts.EXTRACT_SYSTEM},
                                         {"role": "user", "content": user}],
                              purpose="extract", corpus_tokens=evidence.tokens, trace=turn.trace, json_mode=True,
                              max_tokens=900, timeout=turn.timeout())
        try:
            data = parse_json_object(resp.text)
        except ValueError:
            data = {"coverage": "none", "facts": []}
        turn.trace.set("extract", data)
        by_id = evidence.by_id()
        resolutions = []
        ungrounded = []
        for fact in data.get("facts") or []:
            if not isinstance(fact, dict):
                continue
            rule = str(fact.get("rule", "")).strip() or "rule"
            cands = []
            for c in fact.get("candidates") or []:
                if not isinstance(c, dict):
                    continue
                ev = by_id.get(str(c.get("ref", "")).strip("[] "))
                value = str(c.get("value", "")).strip()
                if ev is None or not value:
                    continue
                passage = f"{ev.hit.doc.title}\n{ev.hit.chunk.text}"
                if not is_grounded(value, ev.hit.chunk.text):
                    ungrounded.append({"ref": ev.evidence_id, "doc_id": ev.hit.doc.doc_id, "value": value,
                                       "reason": "number not in passage"})
                    continue
                if not rule_matches_passage(rule, passage):
                    ungrounded.append({"ref": ev.evidence_id, "doc_id": ev.hit.doc.doc_id, "value": value,
                                       "reason": f"passage does not mention '{rule}'"})
                    continue
                cands.append(Candidate(ev.evidence_id, ev.hit.doc, value, ev.hit.chunk.locator,
                                       upcoming=ev.hit.upcoming))
            if cands:
                res = resolve_rule(rule, cands)
                if res.winners or res.upcoming:
                    resolutions.append(res)
        resolutions = drop_redundant_low_authority(resolutions)
        if ungrounded:
            turn.trace.set("ungrounded_candidates", ungrounded)
            log.warning("extract_ungrounded_values", count=len(ungrounded))
        coverage = str(data.get("coverage", "none")).lower()
        if coverage == "none" or not resolutions:
            resolutions = []
        uncovered = str(data.get("uncovered") or "").strip() if coverage != "full" else ""
        return resolutions, uncovered, coverage

    async def _compose(self, turn: Turn, resolutions: list[Resolution], uncovered: str, result: dict) -> str:
        facts_lines = []
        for r in resolutions:
            if r.status == "conflict":
                vals = " | ".join(f'"{w.value}" [{w.doc.doc_id}, {w.locator}]' for w in r.winners)
                facts_lines.append(f"- CONFLICT - {r.rule}: {vals}")
            elif r.winners:
                distinct = {normalize_value(w.value): w for w in r.winners}
                if len(distinct) == 1:
                    srcs = ", ".join(f"[{x.doc.doc_id}, {x.locator}]" for x in r.winners)
                    facts_lines.append(f"- RESOLVED - {r.rule}: \"{r.winners[0].value}\" {srcs}")
                else:  # one document giving values for different conditions (e.g. a rate table)
                    vals = "; ".join(f'"{w.value}" [{w.doc.doc_id}, {w.locator}]' for w in distinct.values())
                    facts_lines.append(f"- RESOLVED (values by condition) - {r.rule}: {vals}")
            if r.upcoming:
                u = r.upcoming
                facts_lines.append(f"  UPCOMING from {u.doc.effective_date} - {r.rule}: \"{u.value}\" "
                                   f"[{u.doc.doc_id}, {u.locator}]")
        facts = "\n".join(facts_lines) or "(none)"
        tool_results = {
            "code_result": result,
            "holiday_and_working_day_results": turn.api.helper_results,
            "tool_calls": [{"name": r.name, "status": r.status, "result": r.result, "error": r.error}
                           for r in turn.ctx.records],
        }
        tool_json = mask_for_user(json.dumps(tool_results, default=str), turn.api.visible_names())[:6000]
        ref_dates = sorted({s["as_of"] for s in turn.api.searches}) or [turn.today.isoformat()]
        user = (f"Question: {turn.message}\n"
                f"Requester: {_requester_line(turn)}\n"
                f"Document facts below are the ones in effect on: {', '.join(ref_dates)}\n\n"
                f"Tool results (JSON):\n{tool_json}\n\nDocument facts:\n{facts}\n"
                + (f"\nNot covered: {uncovered}\n" if uncovered else ""))
        try:
            turn.events.emit("phase", name="compose", label="Writing the answer")
            resp = await call_llm(self.llm, [{"role": "system", "content": prompts.COMPOSE_SYSTEM},
                                             {"role": "user", "content": user}],
                                  purpose="compose", corpus_tokens=count_tokens(facts) if resolutions else 0,
                                  trace=turn.trace, max_tokens=600, timeout=turn.timeout())
            text = clean_brackets((resp.text or "").strip(), set(turn.ctx.corpus.docs))
            if text:
                extra = unsupported_numbers(text, user)
                if extra:
                    turn.trace.set("answer_unsupported_numbers", extra)
                    log.warning("answer_unsupported_numbers", count=len(extra))
                return text
        except LLMError:
            log.warning("compose_failed_fallback")
        # Deterministic fallback so the user still gets the resolved facts.
        lines = [ln.strip("- ") for ln in facts_lines] or ["Here is what I found in your leave data."]
        if uncovered:
            lines.append(f"The documents do not cover: {uncovered}. Please contact the HR team.")
        return "\n".join(lines)


_NUM = re.compile(r"\d+(?:\.\d+)?")
_BRACKET = re.compile(r"\s?\[([^\[\]\n]{1,120})\]")


def clean_brackets(text: str, doc_ids: set[str]) -> str:
    """Keep [..] only when it starts with a real doc_id; drop labels like [tool_result] or [POL-EXAMPLE]."""
    def repl(m: re.Match) -> str:
        head = re.split(r"[,;\s]", m.group(1).strip(), maxsplit=1)[0]
        return m.group(0) if head in doc_ids else ""

    return _BRACKET.sub(repl, text).strip()


def is_grounded(value: str, passage: str) -> bool:
    """A candidate value is kept only if its main quantity (first number) appears in its source passage.

    Catches extractor hallucinations ("10 days" attributed to a passage that never says 10). Only the
    first number is checked: qualifiers the model adds in another format (e.g. "from 2026-07-01" for
    "1 July 2026") must not cause a true value to be dropped.
    """
    nums = _NUM.findall(value)
    if not nums:
        return True
    in_passage = {float(n) for n in _NUM.findall(passage)}
    return float(nums[0]) in in_passage


def service_length(join_date: str, on: date) -> str:
    try:
        joined = date.fromisoformat(join_date)
    except ValueError:
        return "unknown"
    months = (on.year - joined.year) * 12 + (on.month - joined.month) - (1 if on.day < joined.day else 0)
    return f"{months // 12} years {months % 12} months"


def _requester_line(turn: Turn) -> str:
    """Requester facts for prompts. Ids, roles, regions, levels and dates are not personal data (TASK 7.4)."""
    e = turn.employee
    line = (f"employee_id={e.employee_id}, first_name={e.full_name.split()[0] if e.full_name else ''}, "
            f"role={e.role}, region={e.region}, level={e.level}, join_date={e.join_date}, "
            f"today={turn.today.isoformat()}")
    try:  # computed here so the model never has to do date arithmetic
        joined = date.fromisoformat(e.join_date)
        months = (turn.today.year - joined.year) * 12 + (turn.today.month - joined.month)
        if turn.today.day < joined.day:
            months -= 1
        line += (f", length_of_service={months // 12} years {months % 12} months, "
                 f"calendar_months_remaining_this_year_including_current={13 - turn.today.month}")
    except ValueError:
        pass
    return line


def unsupported_numbers(answer: str, sources: str) -> list[str]:
    """Numbers in the answer that appear in no source (facts, tool results, requester line, question).

    Calculated results can legitimately appear here; the list is recorded in the trace for review.
    """
    known = {float(n) for n in _NUM.findall(sources)}
    return sorted({n for n in _NUM.findall(answer) if float(n) not in known and float(n) > 2})


def _citations(resolutions: list[Resolution], structured: list[tuple[str, str]]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(doc_id: str, locator: str) -> None:
        if (doc_id, locator) not in seen:
            seen.add((doc_id, locator))
            out.append({"doc_id": doc_id, "locator": locator})

    for r in resolutions:
        for w in r.winners:
            add(w.doc.doc_id, w.locator)
        if r.upcoming:
            add(r.upcoming.doc.doc_id, r.upcoming.locator)
    for doc_id, loc in structured:
        add(doc_id, loc)
    return out



def mentioned_dates(message: str, today: date) -> list[str]:
    """ISO dates mentioned in a message ("23 November", "2026-11-23"); a date without a year means 2026."""
    from app.ingestion.holidays import MONTHS
    from app.orchestration.dates import _DAY_MONTH, _ISO, _MONTH_DAY, DEFAULT_YEAR

    out: list[str] = []
    for m in _ISO.finditer(message):
        out.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    for rx, d_idx, m_idx in ((_DAY_MONTH, 1, 2), (_MONTH_DAY, 2, 1)):
        for m in rx.finditer(message):
            try:
                year = int(m.group(3)) if m.group(3) else DEFAULT_YEAR
                out.append(date(year, MONTHS[m.group(m_idx).lower()], int(m.group(d_idx))).isoformat())
            except (ValueError, KeyError):
                continue
    return sorted(set(out))
