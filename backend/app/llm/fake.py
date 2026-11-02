"""Scripted LLM for offline tests. Records every message list it receives (for leak checks)."""

from __future__ import annotations

import json
from collections.abc import Callable

from app.llm.base import LLMResponse

Handler = Callable[[list[dict], dict], "str | dict | LLMResponse"]


class FakeLLM:
    provider = "fake"
    model = "fake"

    def __init__(self, handler: Handler | None = None):
        self.handler = handler or (lambda messages, opts: {"action": "refuse", "refuse_reason": "off_topic"})
        self.calls: list[list[dict]] = []

    async def chat(self, messages, *, json_mode=False, tools=None, max_tokens=1500, timeout=20.0) -> LLMResponse:
        self.calls.append(messages)
        out = self.handler(messages, {"json_mode": json_mode, "tools": tools})
        if isinstance(out, LLMResponse):
            return out
        if isinstance(out, dict):
            out = json.dumps(out)
        return LLMResponse(text=out, prompt_tokens=0, completion_tokens=0, model="fake")

    def all_text(self) -> str:
        return "\n".join(json.dumps(m, default=str) for call in self.calls for m in call)
