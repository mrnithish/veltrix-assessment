"""Anthropic Messages API adapter (OpenAI-style messages in, normalized response out)."""

from __future__ import annotations

import json

from anthropic import AsyncAnthropic

from app.llm.base import LLMResponse, ToolCallRequest


def _convert(messages: list[dict]) -> tuple[str, list[dict]]:
    system_parts, out = [], []
    for m in messages:
        role = m["role"]
        if role == "system":
            system_parts.append(m["content"])
        elif role == "tool":
            out.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}]})
        elif role == "assistant" and m.get("tool_calls"):
            blocks = [{"type": "text", "text": m["content"]}] if m.get("content") else []
            for tc in m["tool_calls"]:
                blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"],
                               "input": json.loads(tc["function"]["arguments"] or "{}")})
            out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": role, "content": m["content"]})
    # Anthropic requires alternating roles: merge consecutive same-role text messages.
    merged: list[dict] = []
    for m in out:
        if merged and merged[-1]["role"] == m["role"] and isinstance(m["content"], str) \
                and isinstance(merged[-1]["content"], str):
            merged[-1]["content"] += "\n\n" + m["content"]
        else:
            merged.append(m)
    return "\n\n".join(system_parts), merged


def _tools(tools: list[dict] | None) -> list[dict] | None:
    if not tools:
        return None
    return [
        {"name": t["function"]["name"], "description": t["function"].get("description", ""),
         "input_schema": t["function"]["parameters"]}
        for t in tools
    ]


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, model: str, api_key: str):
        if not api_key:
            raise ValueError("No API key configured for LLM_PROVIDER=anthropic")
        self.model = model
        self._client = AsyncAnthropic(api_key=api_key, max_retries=1)

    async def chat(self, messages, *, json_mode=False, tools=None, max_tokens=1500, timeout=20.0) -> LLMResponse:
        system, msgs = _convert(messages)
        if json_mode:
            system += "\n\nRespond with a single JSON object only."
        kwargs = dict(model=self.model, max_tokens=max_tokens, system=system, messages=msgs, timeout=timeout)
        converted = _tools(tools)
        if converted:
            kwargs["tools"] = converted
        resp = await self._client.messages.create(**kwargs)
        text, calls = [], []
        for block in resp.content:
            if block.type == "text":
                text.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCallRequest(block.id, block.name, dict(block.input or {})))
        return LLMResponse(
            text="".join(text),
            tool_calls=calls,
            prompt_tokens=getattr(resp.usage, "input_tokens", 0) or 0,
            completion_tokens=getattr(resp.usage, "output_tokens", 0) or 0,
            model=resp.model or self.model,
        )
