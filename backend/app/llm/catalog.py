"""Model catalog per provider (live from the provider where possible, merged with a curated list)
and a quick availability probe used by Settings → "Test model"."""

from __future__ import annotations

import re
import time

import httpx

from app.config import DEFAULT_MODELS, Settings
from app.observability.logging import get_logger

log = get_logger(__name__)

# Curated entries (always shown; "note" explains known availability).
CURATED: dict[str, list[dict]] = {
    "nvidia": [
        {"id": "nvidia/nemotron-3.5-lightning-30b-a3b", "note": "default: fast, reliable on the free tier"},
        {"id": "nvidia/nemotron-3-ultra-550b-a55b", "note": "strongest Nemotron; often busy on the free tier"},
        {"id": "nvidia/nemotron-3.5-bolt-e4b", "note": "very fast, small; used as fallback"},
        {"id": "openai/gpt-oss-120b", "note": "returned 410 Gone on NIM at last check; test before use"},
        {"id": "openai/gpt-oss-20b"},
        {"id": "deepseek-ai/deepseek-v4.1-flash"},
        {"id": "mistralai/mistral-large-4-1t-a52b"},
        {"id": "z-ai/glm-5.3-flash"},
        {"id": "minimaxai/minimax-m3.1-flash"},
        {"id": "google/gemma-4-31b-it"},
    ],
    "ollama": [
        {"id": "gpt-oss:120b", "note": "needs Ollama Cloud credits"},
        {"id": "gpt-oss:20b", "note": "needs Ollama Cloud credits"},
        {"id": "glm-5.3-flash"}, {"id": "deepseek-v4.1-flash"}, {"id": "kimi-k3"}, {"id": "mistral-large-4"},
        {"id": "nemotron-3-super"}, {"id": "gemma4:31b"}, {"id": "minimax-m3.1-flash"},
    ],
    "openai": [{"id": "gpt-4.1-mini"}, {"id": "gpt-4.1"}, {"id": "gpt-4o-mini"}, {"id": "gpt-4o"}],
    "anthropic": [{"id": "claude-sonnet-5-5"}, {"id": "claude-haiku-5-5"}, {"id": "claude-opus-5-5"}],
    "gemini": [{"id": "gemini-2.5-flash"}, {"id": "gemini-2.5-pro"}, {"id": "gemini-2.5-flash-lite"}],
}

# Not chat models (embeddings, reward, safety, parsing, vision-only, translation ...).
_NOT_CHAT = re.compile(r"embed|reward|guard|safety|parse|clip|deplot|kosmos|fuyu|vila|neva|detector|calibration|"
                       r"translate|retriever|arctic-embed|recurrentgemma|codegemma|starcoder|diffusion|cosmos|"
                       r"content-safety|topic-control|vlm|vision", re.I)

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_TTL_S = 600


def _key_and_url(settings: Settings, provider: str) -> tuple[str, str | None]:
    if provider == "nvidia":
        return settings.nvidia_api_key, f"{settings.nvidia_base_url.rstrip('/')}/models"
    if provider == "openai":
        return settings.openai_api_key, f"{(settings.openai_base_url or 'https://api.openai.com/v1').rstrip('/')}/models"
    if provider == "ollama":
        base = settings.ollama_base_url.rstrip("/").removesuffix("/v1")
        return settings.ollama_api_key, f"{base}/api/tags"
    if provider == "gemini":
        return settings.google_api_key, "https://generativelanguage.googleapis.com/v1beta/openai/models"
    return "", None


async def _live(settings: Settings, provider: str) -> list[str]:
    key, url = _key_and_url(settings, provider)
    if not key or not url:
        return []
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
        data = r.json()
    if provider == "ollama":
        ids = [m.get("name") or m.get("model") for m in data.get("models", [])]
    else:
        ids = [m.get("id", "").removeprefix("models/") for m in data.get("data", [])]
    if provider == "openai":
        ids = [i for i in ids if re.match(r"^(gpt-|o\d)", i)]
    return sorted({i for i in ids if i and not _NOT_CHAT.search(i)})


async def list_models(settings: Settings, provider: str, refresh: bool = False) -> dict:
    cached = _CACHE.get(provider)
    error = None
    if cached and not refresh and time.time() - cached[0] < _TTL_S:
        live_ids = [m["id"] for m in cached[1]]
    else:
        try:
            live_ids = await _live(settings, provider)
            _CACHE[provider] = (time.time(), [{"id": i} for i in live_ids])
        except Exception as exc:  # provider down or key invalid: curated list still works
            live_ids, error = [], f"{type(exc).__name__}: {str(exc)[:160]}"
            log.warning("model_catalog_failed", provider=provider, error=error)
    curated = {m["id"]: m for m in CURATED.get(provider, [])}
    models = []
    for mid in dict.fromkeys([*curated, *live_ids]):
        models.append({
            "id": mid,
            "listed_by_provider": mid in live_ids,
            "curated": mid in curated,
            "default": mid == DEFAULT_MODELS.get(provider),
            "note": curated.get(mid, {}).get("note"),
        })
    return {"provider": provider, "models": models, "live_count": len(live_ids), "error": error}


async def probe_model(settings: Settings, provider: str, model: str) -> dict:
    """One tiny request to the exact model (no fallbacks) to show availability and latency."""
    from app.llm import make_llm

    client = make_llm(settings, provider, model)
    if hasattr(client, "fallback_models"):
        client.fallback_models = []
    t0 = time.perf_counter()
    try:
        resp = await client.chat([{"role": "user", "content": "Reply with the single word OK."}], max_tokens=20,
                                 timeout=20)
        return {"ok": True, "provider": provider, "model": model, "latency_ms": round((time.perf_counter() - t0) * 1000),
                "reply": (resp.text or "")[:40]}
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        return {"ok": False, "provider": provider, "model": model, "status": status,
                "latency_ms": round((time.perf_counter() - t0) * 1000),
                "error": {410: "Model retired by the provider (410 Gone)", 402: "Account needs credits (402)",
                          404: "Model not found (404)", 401: "API key rejected (401)",
                          503: "Provider overloaded (503)"}.get(status, f"{type(exc).__name__}: {str(exc)[:160]}")}
