"""Model fallback and hedged requests in the OpenAI-compatible client (no network)."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError

from app.llm import PROVIDERS, current_selection, reset_selection, set_selection
from app.llm.openai_compat import OpenAICompatClient


def _reply(text):
    msg = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None, model="")


class ScriptedClient(OpenAICompatClient):
    def __init__(self, behaviour: dict, hedge_after_s=0.2):
        super().__init__("nvidia", "primary", "key", "http://x", ["fallback"])
        self.behaviour = behaviour
        self.hedge_after_s = hedge_after_s
        self.started: list[str] = []

    async def _create(self, kwargs):
        model = kwargs["model"]
        self.started.append(model)
        delay, outcome = self.behaviour[model]
        await asyncio.sleep(delay)
        if outcome == "timeout":
            raise APITimeoutError(request=httpx.Request("POST", "http://x"))
        return _reply(f"from {model}")


def test_primary_answers():
    c = ScriptedClient({"primary": (0.01, "ok"), "fallback": (0.01, "ok")})
    r = asyncio.run(c.chat([{"role": "user", "content": "hi"}], timeout=5))
    assert r.text == "from primary" and r.model == "primary" and c.started == ["primary"]


def test_falls_back_when_primary_fails():
    c = ScriptedClient({"primary": (0.01, "timeout"), "fallback": (0.01, "ok")})
    r = asyncio.run(c.chat([{"role": "user", "content": "hi"}], timeout=5))
    assert r.model == "fallback"


def test_hedges_when_primary_is_slow():
    c = ScriptedClient({"primary": (3.0, "ok"), "fallback": (0.05, "ok")}, hedge_after_s=0.2)
    r = asyncio.run(c.chat([{"role": "user", "content": "hi"}], timeout=5))
    assert r.model == "fallback" and c.started == ["primary", "fallback"]


def test_all_models_failing_raises():
    c = ScriptedClient({"primary": (0.01, "timeout"), "fallback": (0.01, "timeout")})
    with pytest.raises(APITimeoutError):
        asyncio.run(c.chat([{"role": "user", "content": "hi"}], timeout=5))


def test_runtime_provider_switch(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    get_settings.cache_clear()
    try:
        s = get_settings()
        sel = set_selection(s, "nvidia", None, "tools")
        assert sel.model and sel.agent_mode == "tools"
        assert current_selection(s).provider == "nvidia"
        with pytest.raises(ValueError):
            set_selection(s, "openai", None, None)  # no key configured
        with pytest.raises(ValueError):
            set_selection(s, "nope", None, None)
        assert "nvidia" in PROVIDERS
    finally:
        reset_selection()
        get_settings.cache_clear()
