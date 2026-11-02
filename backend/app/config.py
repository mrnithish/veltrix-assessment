"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATA = _REPO_ROOT / "data"

# Default model per provider; LLM_MODEL overrides.
DEFAULT_MODELS = {
    "nvidia": "nvidia/nemotron-3.5-lightning-30b-a3b",
    "ollama": "gpt-oss:120b",
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-sonnet-5-5",
    "gemini": "gemini-2.5-flash",
    "fake": "fake",
}

# Tried in order when the primary model times out, is overloaded or missing. LLM_FALLBACK_MODELS overrides.
DEFAULT_FALLBACKS = {
    "nvidia": ("nvidia/nemotron-3.5-bolt-e4b", "nvidia/nemotron-3-ultra-550b-a55b"),
}

CORPUS_TOKEN_BUDGET = 3000


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    corpus_dir: Path
    manifest_path: Path
    db_path: Path
    state_db_path: Path
    app_today: str
    app_timezone: str
    llm_provider: str
    llm_model: str
    llm_fallback_models: tuple[str, ...]
    llm_timeout_s: float
    nvidia_api_key: str
    nvidia_base_url: str
    ollama_api_key: str
    ollama_base_url: str
    openai_api_key: str
    openai_base_url: str
    anthropic_api_key: str
    google_api_key: str
    agent_mode: str
    qdrant_url: str
    embedding_backend: str
    embedding_model: str
    otel_endpoint: str
    log_level: str
    dev_endpoints: bool
    cors_origins: tuple[str, ...]
    phoenix_ui_url: str

    @property
    def model(self) -> str:
        return self.llm_model or DEFAULT_MODELS.get(self.llm_provider, "")

    def fallbacks_for(self, provider: str) -> list[str]:
        if provider == self.llm_provider and self.llm_fallback_models:
            return list(self.llm_fallback_models)
        return list(DEFAULT_FALLBACKS.get(provider, ()))


def _auto_provider() -> str:
    """LLM_PROVIDER=auto (or unset): use whichever provider has an API key."""
    for provider, key in (("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY"),
                          ("gemini", "GOOGLE_API_KEY"), ("nvidia", "NVIDIA_API_KEY"),
                          ("ollama", "OLLAMA_API_KEY")):
        if _env(key):
            return provider
    return "nvidia"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    provider = _env("LLM_PROVIDER", "auto").lower()
    if provider == "auto":
        provider = _auto_provider()
    return Settings(
        corpus_dir=Path(_env("CORPUS_DIR", str(_DEFAULT_DATA / "corpus"))),
        manifest_path=Path(_env("MANIFEST_PATH", str(_DEFAULT_DATA / "manifest.json"))),
        db_path=Path(_env("DB_PATH", str(_DEFAULT_DATA / "veltrix.db"))),
        state_db_path=Path(_env("STATE_DB_PATH", str(_REPO_ROOT / "state" / "app_state.db"))),
        app_today=_env("APP_TODAY"),
        app_timezone=_env("APP_TIMEZONE", _env("TZ", "UTC")),
        llm_provider=provider,
        llm_model=_env("LLM_MODEL"),
        llm_fallback_models=tuple(m.strip() for m in _env("LLM_FALLBACK_MODELS").split(",") if m.strip()),
        llm_timeout_s=float(_env("LLM_TIMEOUT_S", "20")),
        nvidia_api_key=_env("NVIDIA_API_KEY"),
        nvidia_base_url=_env("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        ollama_api_key=_env("OLLAMA_API_KEY"),
        ollama_base_url=_env("OLLAMA_BASE_URL", "https://ollama.com/v1"),
        openai_api_key=_env("OPENAI_API_KEY"),
        openai_base_url=_env("OPENAI_BASE_URL"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        google_api_key=_env("GOOGLE_API_KEY"),
        agent_mode=_env("AGENT_MODE", "codemode").lower(),
        qdrant_url=_env("QDRANT_URL"),
        embedding_backend=_env("EMBEDDING_BACKEND", "fastembed").lower(),
        embedding_model=_env("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        otel_endpoint=_env("OTEL_EXPORTER_OTLP_ENDPOINT"),
        log_level=_env("LOG_LEVEL", "INFO").upper(),
        dev_endpoints=_env("DEV_ENDPOINTS", "true").lower() in ("1", "true", "yes"),
        cors_origins=tuple(o.strip() for o in _env("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()),
        phoenix_ui_url=_env("PHOENIX_UI_URL", "http://localhost:6006"),
    )


def app_tz() -> ZoneInfo:
    """Timezone used for "today" (APP_TIMEZONE, e.g. Asia/Kolkata). Containers run in UTC by default, so
    without it the date would be wrong for part of the day in other zones."""
    name = os.environ.get("APP_TIMEZONE") or get_settings().app_timezone or "UTC"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def now() -> datetime:
    """Current date-time in the app timezone. If APP_TODAY pins the date, that date is kept with the current time."""
    current = datetime.now(app_tz())
    pinned = os.environ.get("APP_TODAY") or get_settings().app_today
    if pinned:
        d = date.fromisoformat(pinned)
        current = current.replace(year=d.year, month=d.month, day=d.day)
    return current


def today() -> date:
    """APP_TODAY if set, else today's date in APP_TIMEZONE. Read on every call so tests can change it."""
    value = os.environ.get("APP_TODAY") or get_settings().app_today
    return date.fromisoformat(value) if value else datetime.now(app_tz()).date()
