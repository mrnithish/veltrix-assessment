"""HTTP endpoints: POST /chat, GET /health, GET /metrics, GET /traces/{id}, dev helpers."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import ValidationError

from app.api.schemas import ChatRequest, ChatResponse
from app.config import get_settings
from app.data import repositories as repo
from app.data import state
from app.identity.auth import AuthError, check_session_owner, resolve_requester
from app.ingestion.pipeline import corpus_ready, get_corpus
from app.llm import current_selection, make_llm, providers_status, reset_selection, set_selection
from app.observability import metrics
from app.observability.logging import bind_context, clear_context, get_logger
from app.orchestration.agent import UNAVAILABLE, Agent, ChatResult
from app.orchestration.events import EventSink

log = get_logger(__name__)
router = APIRouter()

CHAT_TIMEOUT_S = 29.0
_session_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_agent: Agent | None = None


def get_agent() -> Agent:
    global _agent
    if _agent is None:
        settings = get_settings()
        sel = current_selection(settings)
        _agent = Agent(make_llm(settings, sel.provider, sel.model), sel.agent_mode)
    return _agent


def reset_agent() -> None:
    global _agent
    _agent = None


def _error(status: int, detail: str) -> JSONResponse:
    metrics.HTTP_ERRORS.labels(str(status)).inc()
    return JSONResponse(status_code=status, content={"detail": detail})


@router.get("/health")
def health():
    if not corpus_ready():
        return JSONResponse(status_code=503, content={"status": "starting"})
    return {"status": "ok"}


@router.get("/metrics")
def prometheus_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


async def _prepare_chat(request: Request, request_id: str):
    """Shared validation for /chat and /chat/stream: (employee, body) or an error response."""
    clear_context()
    bind_context(request_id=request_id)
    if not corpus_ready():
        return _error(503, "Service is starting; ingestion has not finished")
    try:
        employee = resolve_requester(request.headers.get("X-Employee-Id"))
    except AuthError as exc:
        log.info("chat_rejected", status=exc.status)
        return _error(exc.status, exc.detail)
    try:
        raw = await request.body()
        body = ChatRequest.model_validate(json.loads(raw or b"null"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, TypeError, ValueError):
        log.info("chat_rejected", status=400)
        return _error(400, "Body must be JSON with non-empty 'session_id' and 'message' strings")
    bind_context(session_id=body.session_id, employee_id=employee.employee_id)
    try:
        check_session_owner(body.session_id, employee)
    except AuthError as exc:
        log.info("chat_rejected", status=exc.status)
        return _error(exc.status, exc.detail)
    log.info("chat_request", message_chars=len(body.message))
    return employee, body


async def _run_agent(employee, body: ChatRequest, request_id: str, events=None) -> ChatResult:
    async with _session_locks[body.session_id]:
        try:
            return await asyncio.wait_for(
                get_agent().handle(employee, body.session_id, body.message, request_id, events=events),
                timeout=CHAT_TIMEOUT_S,
            )
        except TimeoutError:
            log.error("chat_timeout")
        except Exception:
            log.exception("chat_failed")
    return ChatResult(request_id, UNAVAILABLE, "no_answer")


@router.post("/chat")
async def chat(request: Request):
    request_id = str(uuid.uuid4())
    prepared = await _prepare_chat(request, request_id)
    if isinstance(prepared, JSONResponse):
        return prepared
    employee, body = prepared
    result = await _run_agent(employee, body, request_id)
    response = ChatResponse.model_validate(result.to_dict())
    return JSONResponse(content=response.model_dump())


@router.post("/chat/stream")
async def chat_stream(request: Request):
    """Same as /chat, but streams the agent's steps as Server-Sent Events (the UI's live "thinking").

    Events: start, phase, plan, call, call_done, sandbox, llm, evidence, resolution, note, final.
    The final event carries exactly the /chat response body.
    """
    request_id = str(uuid.uuid4())
    prepared = await _prepare_chat(request, request_id)
    if isinstance(prepared, JSONResponse):
        return prepared
    employee, body = prepared
    sink = EventSink()

    async def run() -> None:
        try:
            result = await _run_agent(employee, body, request_id, events=sink)
            if result.answer == UNAVAILABLE:  # timeout/failure paths do not emit their own final event
                sink.emit("final", response=ChatResponse.model_validate(result.to_dict()).model_dump())
        finally:
            sink.close()

    task = asyncio.create_task(run())

    async def stream():
        sent_final = False
        while True:
            event = await sink.queue.get()
            if event is None:
                break
            if event["type"] == "final":
                if sent_final:
                    continue
                sent_final = True
            yield f"data: {json.dumps(event, default=str)}\n\n"
        await task

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/traces/{request_id}")
def get_trace(request_id: str, request: Request):
    """Full trace of one answer. Only the employee who asked can read it."""
    try:
        employee = resolve_requester(request.headers.get("X-Employee-Id"))
    except AuthError as exc:
        return _error(exc.status, exc.detail)
    trace = state.get_trace(request_id)
    if trace is None or trace["employee_id"] != employee.employee_id:
        return _error(404, "Trace not found")
    return trace["payload"]


@router.get("/dev/employees")
def dev_employees():
    """For the demo UI: ids, roles and regions only (no names, emails or phones)."""
    if not get_settings().dev_endpoints:
        return _error(404, "Not found")
    return [
        {"employee_id": e.employee_id, "role": e.role, "region": e.region, "level": e.level,
         "manager_id": e.manager_id}
        for e in repo.list_employees()
    ]


@router.get("/dev/info")
def dev_info():
    if not get_settings().dev_endpoints:
        return _error(404, "Not found")
    s = get_settings()
    sel = current_selection(s)
    info = {"llm_provider": sel.provider, "llm_model": sel.model, "agent_mode": sel.agent_mode,
            "ready": corpus_ready(), "phoenix_url": s.phoenix_ui_url if s.otel_endpoint else None}
    if corpus_ready():
        stats = dict(get_corpus().stats)
        stats.pop("per_doc", None)
        info["ingestion"] = stats
    return info


@router.get("/llm")
def get_llm():
    """Current LLM provider/model/agent mode and which providers have keys configured."""
    s = get_settings()
    sel = current_selection(s)
    return {"provider": sel.provider, "model": sel.model, "agent_mode": sel.agent_mode,
            "providers": providers_status(s), **_resilience(s, sel.provider)}


def _resilience(settings, provider: str) -> dict:
    import os

    return {"fallbacks": settings.fallbacks_for(provider),
            "hedge_after_s": float(os.environ.get("LLM_HEDGE_AFTER_S", "4")),
            "llm_timeout_s": settings.llm_timeout_s, "request_deadline_s": 26, "corpus_token_budget": 3000}


@router.post("/llm")
async def switch_llm(request: Request):
    """Switch provider/model/agent mode at runtime (demo/admin; disabled when DEV_ENDPOINTS=false)."""
    s = get_settings()
    if not s.dev_endpoints:
        return _error(404, "Not found")
    try:
        body = json.loads(await request.body() or b"null")
        if not isinstance(body, dict):
            raise ValueError("body must be a JSON object")
        if body.get("reset"):
            reset_selection()
        else:
            set_selection(s, str(body.get("provider") or "").lower(), body.get("model"), body.get("agent_mode"))
    except (json.JSONDecodeError, ValueError) as exc:
        return _error(400, str(exc))
    reset_agent()
    sel = current_selection(s)
    log.info("llm_switched", provider=sel.provider, model=sel.model, agent_mode=sel.agent_mode)
    return {"provider": sel.provider, "model": sel.model, "agent_mode": sel.agent_mode,
            "providers": providers_status(s)}


@router.get("/llm/models")
async def llm_models(provider: str, refresh: bool = False):
    """Model catalog: live list from the provider (when a key is set) merged with a curated list."""
    from app.llm.catalog import list_models

    return await list_models(get_settings(), provider.lower(), refresh=refresh)


@router.post("/llm/test")
async def llm_test(request: Request):
    """Probe one exact model (no fallbacks): availability + latency, before switching to it."""
    from app.llm import provider_configured
    from app.llm.catalog import probe_model

    if not get_settings().dev_endpoints:
        return _error(404, "Not found")
    try:
        body = json.loads(await request.body() or b"null")
        provider, model = str(body["provider"]).lower(), str(body["model"]).strip()
    except (json.JSONDecodeError, KeyError, TypeError):
        return _error(400, "Body must be JSON with 'provider' and 'model'")
    if not provider_configured(get_settings(), provider):
        return _error(400, f"No API key configured for {provider}")
    return await probe_model(get_settings(), provider, model)


@router.get("/usage")
def usage(days: int = 14, request: Request = None):
    """Token consumption, latency and fallback statistics (no personal data).

    With a signed-in user's token, also returns that user's own usage under "mine".
    """
    from app.identity.tokens import verify_token

    days = max(1, min(int(days), 90))
    out = state.usage_summary(days)
    auth = request.headers.get("Authorization", "") if request else ""
    employee_id = verify_token(auth[7:].strip()) if auth.lower().startswith("bearer ") else None
    if employee_id:
        out["mine"] = state.usage_summary(days, employee_id)["totals"]
    return out
