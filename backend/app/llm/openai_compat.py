"""OpenAI-compatible chat API: used for NVIDIA NIM, OpenAI, Google Gemini and Ollama Cloud.

Resilience:
  * adapts once to unsupported parameters (response_format, max_tokens, temperature, seed, extra_body)
  * model fallback chain (LLM_FALLBACK_MODELS): if the primary model fails (timeout, overload, missing),
    the next model is tried; if it is merely slow (> LLM_HEDGE_AFTER_S), the next model is started in
    parallel and the first good reply wins ("hedged requests").
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    RateLimitError,
)

from app.llm.base import LLMResponse, ToolCallRequest
from app.observability.logging import get_logger

log = get_logger(__name__)

_THINK = re.compile(r"<think>.*?</think>", re.S)
_FALLBACK_ERRORS = (APITimeoutError, APIConnectionError, InternalServerError, NotFoundError, RateLimitError)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Request extras per provider. NVIDIA NIM: turn off hidden "thinking" so answers stay fast.
PROVIDER_EXTRA_BODY = {
    "nvidia": {"chat_template_kwargs": {"enable_thinking": False}},
}


class OpenAICompatClient:
    def __init__(self, provider: str, model: str, api_key: str, base_url: str | None = None,
                 fallback_models: list[str] | None = None):
        if not api_key:
            raise ValueError(f"No API key configured for LLM_PROVIDER={provider}")
        self.provider = provider
        self.model = model
        self.fallback_models = [m for m in (fallback_models or []) if m and m != model]
        # Start the next model in parallel when the current one has not answered after this many seconds.
        self.hedge_after_s = float(os.environ.get("LLM_HEDGE_AFTER_S", "4"))
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url or None, max_retries=0)
        self._json_mode_supported = True
        # Adaptations learned from earlier 400 responses, reused for later calls.
        self._dropped: set[str] = set()
        self._use_max_completion_tokens = False
        extra = os.environ.get("LLM_EXTRA_BODY", "").strip()
        self._extra_body = json.loads(extra) if extra else PROVIDER_EXTRA_BODY.get(provider)

    def _kwargs(self, model: str, messages, json_mode, tools, max_tokens, timeout) -> dict:
        kwargs = dict(model=model, messages=messages, temperature=0, max_tokens=max_tokens, timeout=timeout)
        if self.provider in ("openai", "ollama", "nvidia"):
            kwargs["seed"] = 7
        if self._extra_body:
            kwargs["extra_body"] = self._extra_body
        if tools:
            kwargs["tools"] = tools
        if json_mode and self._json_mode_supported and not tools:
            kwargs["response_format"] = {"type": "json_object"}
        for name in self._dropped:
            kwargs.pop(name, None)
        if self._use_max_completion_tokens:
            kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
        return kwargs

    async def _hedged(self, messages, json_mode, tools, max_tokens, timeout):
        """Primary model first; start the next model when the current one fails, or in parallel ("hedge")
        when it is slow. The first successful reply wins and the others are cancelled."""
        deadline = time.monotonic() + timeout
        models = [self.model, *self.fallback_models]
        running: dict[asyncio.Task, str] = {}
        started: dict[asyncio.Task, float] = {}
        attempts: list[dict] = []
        next_i, last_exc = 0, None
        t_start = time.monotonic()

        def record(task: asyncio.Task, model: str, outcome: str) -> None:
            attempts.append({"model": model, "outcome": outcome,
                             "ms": round((time.monotonic() - started.get(task, t_start)) * 1000)})

        def launch() -> None:
            nonlocal next_i
            model = models[next_i]
            next_i += 1
            budget = max(1.0, deadline - time.monotonic())
            task = asyncio.create_task(self._create(self._kwargs(model, messages, json_mode, tools, max_tokens, budget)))
            running[task] = model
            started[task] = time.monotonic()

        launch()
        try:
            while running:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                can_hedge = next_i < len(models)
                wait_for = min(remaining, self.hedge_after_s) if can_hedge else remaining
                done, _ = await asyncio.wait(running, timeout=wait_for, return_when=asyncio.FIRST_COMPLETED)
                if not done:  # slow: hedge with the next model
                    if can_hedge:
                        slow = next(iter(running))
                        attempts.append({"model": running[slow], "outcome": "slow", "ms": round(
                            (time.monotonic() - started[slow]) * 1000)})
                        log.warning("llm_model_hedge", provider=self.provider, slow_model=running[next(iter(running))],
                                    next_model=models[next_i])
                        launch()
                    continue
                for task in done:
                    model = running.pop(task)
                    exc = task.exception()
                    if exc is None:
                        record(task, model, "ok")
                        for other, other_model in running.items():
                            record(other, other_model, "cancelled")
                        return task.result(), model, attempts
                    if not isinstance(exc, _FALLBACK_ERRORS):
                        raise exc
                    last_exc = exc
                    record(task, model, "timeout" if isinstance(exc, APITimeoutError) else
                           f"error {getattr(exc, 'status_code', '') or type(exc).__name__}".strip())
                    log.warning("llm_model_fallback", provider=self.provider, model=model,
                                error=f"{type(exc).__name__}: {str(exc)[:160]}",
                                next_model=models[next_i] if next_i < len(models) else None)
                    if next_i < len(models) and deadline - time.monotonic() > 1.5:
                        launch()
        finally:
            for task in running:
                task.cancel()
        for task, model in running.items():
            record(task, model, "timeout")
        error = last_exc or TimeoutError("LLM call timed out")
        error.attempts = attempts  # type: ignore[attr-defined]  # surfaced in usage records and traces
        raise error

    async def _create(self, kwargs: dict):
        for _attempt in range(5):
            try:
                return await self._client.chat.completions.create(**kwargs)
            except BadRequestError as exc:
                # Adapt once per unsupported parameter, then retry.
                msg = str(exc).lower()
                if "response_format" in msg and "response_format" in kwargs:
                    self._json_mode_supported = False
                    kwargs.pop("response_format")
                elif "max_tokens" in msg and "max_tokens" in kwargs:
                    kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
                    self._use_max_completion_tokens = True
                elif "temperature" in msg and "temperature" in kwargs:
                    kwargs.pop("temperature")
                    self._dropped.add("temperature")
                elif "seed" in msg and "seed" in kwargs:
                    kwargs.pop("seed")
                    self._dropped.add("seed")
                elif ("chat_template" in msg or "extra" in msg) and "extra_body" in kwargs:
                    kwargs.pop("extra_body")
                    self._dropped.add("extra_body")
                else:
                    raise
        raise RuntimeError("LLM request failed after parameter adaptation")

    async def chat(self, messages, *, json_mode=False, tools=None, max_tokens=1500, timeout=20.0) -> LLMResponse:
        resp, used, attempts = await self._hedged(messages, json_mode, tools, max_tokens, timeout)
        choice = resp.choices[0].message
        calls = []
        for tc in choice.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCallRequest(tc.id, tc.function.name, args if isinstance(args, dict) else {}))
        usage = resp.usage
        return LLMResponse(
            text=_THINK.sub("", choice.content or "").strip(),  # reasoning models may inline <think>
            tool_calls=calls,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            model=used,
            attempts=attempts,
        )
