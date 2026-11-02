"""Provider-neutral LLM interface plus the single entry point every call goes through."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.observability import metrics
from app.observability.logging import get_logger
from app.observability.pii import scrub_for_logs
from app.observability.tracing import RequestTrace, tracer
from app.retrieval.budget import assert_within_budget

log = get_logger(__name__)


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    # Fallback/hedging telemetry: [{"model", "outcome": ok|timeout|error|slow|cancelled, "ms"}]
    attempts: list[dict] = field(default_factory=list)


class LLMClient(Protocol):
    provider: str
    model: str

    async def chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        tools: list[dict] | None = None,
        max_tokens: int = 1500,
        timeout: float = 20.0,
    ) -> LLMResponse: ...


class LLMError(RuntimeError):
    pass


async def call_llm(
    client: LLMClient,
    messages: list[dict],
    *,
    purpose: str,
    corpus_tokens: int,
    trace: RequestTrace | None = None,
    json_mode: bool = False,
    tools: list[dict] | None = None,
    max_tokens: int = 1500,
    timeout: float = 20.0,
) -> LLMResponse:
    """Budget check -> provider call -> span, log line (with corpus_tokens), metrics, trace record."""
    assert_within_budget(corpus_tokens)
    t0 = time.perf_counter()
    outcome = "ok"
    with tracer().start_as_current_span(f"llm.{purpose}") as span:
        span.set_attribute("openinference.span.kind", "LLM")
        span.set_attribute("llm.provider", client.provider)
        span.set_attribute("llm.model_name", client.model)
        span.set_attribute("llm.corpus_tokens", corpus_tokens)
        span.set_attribute("input.value", scrub_for_logs(json.dumps(messages, default=str))[:20000])
        try:
            resp = await client.chat(messages, json_mode=json_mode, tools=tools, max_tokens=max_tokens,
                                     timeout=timeout)
        except Exception as exc:
            outcome = "error"
            span.record_exception(exc)
            log.error("llm_call_failed", purpose=purpose, provider=client.provider, model=client.model,
                      corpus_tokens=corpus_tokens, error=f"{type(exc).__name__}: {str(exc)[:300]}")
            _record_usage(trace, client, purpose, corpus_tokens, None, time.perf_counter() - t0,
                          f"{type(exc).__name__}: {str(exc)[:200]}", getattr(exc, "attempts", []))
            raise LLMError(f"{type(exc).__name__}: {str(exc)[:300]}") from exc
        finally:
            elapsed = time.perf_counter() - t0
            metrics.LLM_CALLS.labels(purpose, outcome).inc()
            metrics.LLM_LATENCY.labels(purpose).observe(elapsed)
            metrics.CORPUS_TOKENS.labels(purpose).observe(corpus_tokens)
        span.set_attribute("llm.token_count.prompt", resp.prompt_tokens)
        span.set_attribute("llm.token_count.completion", resp.completion_tokens)
        span.set_attribute("output.value", scrub_for_logs(resp.text or json.dumps(
            [t.__dict__ for t in resp.tool_calls]))[:20000])
    metrics.LLM_TOKENS.labels(purpose, "prompt").inc(resp.prompt_tokens)
    metrics.LLM_TOKENS.labels(purpose, "completion").inc(resp.completion_tokens)
    record = {
        "purpose": purpose,
        "provider": client.provider,
        "model": resp.model or client.model,
        "requested_model": client.model,
        "corpus_tokens": corpus_tokens,
        "prompt_tokens": resp.prompt_tokens,
        "completion_tokens": resp.completion_tokens,
        "latency_ms": round(elapsed * 1000, 1),
        "attempts": resp.attempts,
        "fallback_used": (resp.model or client.model) != client.model,
    }
    log.info("llm_call", **record)
    _record_usage(trace, client, purpose, corpus_tokens, resp, elapsed, None, resp.attempts)
    if trace is not None:
        trace.llm_calls.append(record)
        sink = getattr(trace, "events", None)
        if sink is not None:
            sink.emit("llm", **record)
    return resp


def _record_usage(trace, client, purpose, corpus_tokens, resp, elapsed, error, attempts) -> None:
    """One row per LLM call in llm_usage (token consumption dashboard). Never breaks the request."""
    try:
        from app.data import state

        state.record_llm_usage({
            "request_id": getattr(trace, "request_id", None),
            "employee_id": getattr(trace, "employee_id", None),
            "provider": client.provider,
            "requested_model": client.model,
            "model": (resp.model if resp is not None else None) or client.model,
            "purpose": purpose,
            "prompt_tokens": resp.prompt_tokens if resp is not None else 0,
            "completion_tokens": resp.completion_tokens if resp is not None else 0,
            "corpus_tokens": corpus_tokens,
            "latency_ms": round(elapsed * 1000, 1),
            "outcome": "ok" if error is None else "error",
            "error": error,
            "attempts": attempts or [],
        })
    except Exception:  # usage accounting must never fail a request
        log.exception("usage_record_failed")


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object in a model reply (tolerates code fences and leading prose)."""
    text = (text or "").strip()
    candidates = [text]
    candidates += [m.group(1).strip() for m in _FENCE.finditer(text)]
    start = text.find("{")
    if start >= 0:
        candidates.append(text[start:])
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        # Trim to the last closing brace that still parses.
        s = cand.find("{")
        if s < 0:
            continue
        depth, in_str, esc = 0, False, False
        for i, ch in enumerate(cand[s:], start=s):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(cand[s:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        break
    raise ValueError("no JSON object found in model output")
