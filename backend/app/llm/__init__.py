"""LLM providers and the runtime selection.

LLM_PROVIDER = nvidia | openai | anthropic | gemini | ollama | auto | fake.
The provider/model/agent mode can also be switched at runtime (POST /llm, or the UI);
the choice lives in memory and resets to the environment defaults on restart.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from app.config import DEFAULT_MODELS, Settings

_override = None


def set_llm_override(client) -> None:
    """Tests inject a FakeLLM here."""
    global _override
    _override = client


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    label: str
    key_env: str
    suggested_models: tuple[str, ...]


PROVIDERS: dict[str, ProviderInfo] = {
    "nvidia": ProviderInfo("nvidia", "NVIDIA NIM", "NVIDIA_API_KEY", (
        "nvidia/nemotron-3.5-lightning-30b-a3b", "nvidia/nemotron-3-ultra-550b-a55b",
        "nvidia/nemotron-3.5-bolt-e4b", "deepseek-ai/deepseek-v4.1-flash", "z-ai/glm-5.3-flash",
        "openai/gpt-oss-20b")),
    "openai": ProviderInfo("openai", "OpenAI", "OPENAI_API_KEY", ("gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini")),
    "anthropic": ProviderInfo("anthropic", "Anthropic", "ANTHROPIC_API_KEY",
                              ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5")),
    "gemini": ProviderInfo("gemini", "Google Gemini", "GOOGLE_API_KEY", ("gemini-2.5-flash", "gemini-2.5-pro")),
    "ollama": ProviderInfo("ollama", "Ollama Cloud", "OLLAMA_API_KEY", ("gpt-oss:120b", "gpt-oss:20b")),
}


def _api_key(settings: Settings, provider: str) -> str:
    return {
        "nvidia": settings.nvidia_api_key,
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "gemini": settings.google_api_key,
        "ollama": settings.ollama_api_key,
    }.get(provider, "")


def provider_configured(settings: Settings, provider: str) -> bool:
    return provider == "fake" or bool(_api_key(settings, provider))


def make_llm(settings: Settings, provider: str | None = None, model: str | None = None):
    if _override is not None:
        return _override
    provider = provider or settings.llm_provider
    model = model or (settings.model if provider == settings.llm_provider else DEFAULT_MODELS.get(provider, ""))
    key = _api_key(settings, provider)
    if provider == "nvidia":
        from app.llm.openai_compat import OpenAICompatClient

        return OpenAICompatClient("nvidia", model, key, settings.nvidia_base_url, settings.fallbacks_for("nvidia"))
    if provider == "ollama":
        from app.llm.openai_compat import OpenAICompatClient

        return OpenAICompatClient("ollama", model, key, settings.ollama_base_url, settings.fallbacks_for("ollama"))
    if provider == "openai":
        from app.llm.openai_compat import OpenAICompatClient

        return OpenAICompatClient("openai", model, key, settings.openai_base_url or None, settings.fallbacks_for("openai"))
    if provider == "gemini":
        from app.llm.openai_compat import GEMINI_BASE_URL, OpenAICompatClient

        return OpenAICompatClient("gemini", model, key, GEMINI_BASE_URL, settings.fallbacks_for("gemini"))
    if provider == "anthropic":
        from app.llm.anthropic_client import AnthropicClient

        return AnthropicClient(model, key)
    if provider == "fake":
        from app.llm.fake import FakeLLM

        return FakeLLM()
    raise ValueError(f"Unknown LLM_PROVIDER '{provider}'")


# ---- runtime selection -----------------------------------------------------------------------

@dataclass
class Selection:
    provider: str
    model: str
    agent_mode: str


_lock = threading.Lock()
_selection: Selection | None = None


def current_selection(settings: Settings) -> Selection:
    with _lock:
        if _selection is None:
            return Selection(settings.llm_provider, settings.model, settings.agent_mode)
        return Selection(_selection.provider, _selection.model, _selection.agent_mode)


def set_selection(settings: Settings, provider: str, model: str | None, agent_mode: str | None) -> Selection:
    global _selection
    if provider not in PROVIDERS and provider != "fake":
        raise ValueError(f"Unknown provider '{provider}'. Choose one of: {', '.join(PROVIDERS)}")
    if not provider_configured(settings, provider):
        raise ValueError(f"No API key configured for {provider} (set {PROVIDERS[provider].key_env}).")
    mode = (agent_mode or current_selection(settings).agent_mode).lower()
    if mode not in ("codemode", "tools"):
        raise ValueError("agent_mode must be 'codemode' or 'tools'")
    chosen = (model or "").strip() or DEFAULT_MODELS.get(provider, "")
    with _lock:
        _selection = Selection(provider, chosen, mode)
        return Selection(provider, chosen, mode)


def reset_selection() -> None:
    global _selection
    with _lock:
        _selection = None


def providers_status(settings: Settings) -> list[dict]:
    return [
        {"provider": p.name, "label": p.label, "configured": provider_configured(settings, p.name),
         "key_env": p.key_env, "default_model": DEFAULT_MODELS.get(p.name, ""),
         "suggested_models": list(p.suggested_models)}
        for p in PROVIDERS.values()
    ]
