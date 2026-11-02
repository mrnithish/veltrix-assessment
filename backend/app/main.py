"""FastAPI application. Ingestion starts in the background; /health is 503 until it finishes."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.applications import Starlette
from starlette.routing import Mount

from app.api.app_routes import router as app_router
from app.api.routes import router
from app.config import get_settings
from app.data import repositories as repo
from app.data.state import init_state_db
from app.ingestion.pipeline import run_ingestion, set_corpus
from app.observability.logging import configure_logging, get_logger
from app.observability.pii import register_people
from app.observability.tracing import setup_tracing

log = get_logger(__name__)
_mcp_mount = Mount("/mcp", app=Starlette())  # real app attached in lifespan


async def _ingest_in_background() -> None:
    settings = get_settings()
    attempt = 0
    while True:
        attempt += 1
        try:
            corpus = await asyncio.to_thread(run_ingestion, settings)
            set_corpus(corpus)
            return
        except Exception as exc:
            log.exception("ingestion_error", attempt=attempt, error=str(exc)[:300])
            await asyncio.sleep(min(30, 5 * attempt))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    setup_tracing(settings.otel_endpoint)
    init_state_db()
    register_people(repo.list_employees())
    log.info("startup", provider=settings.llm_provider, model=settings.model, agent_mode=settings.agent_mode,
             corpus_dir=str(settings.corpus_dir), tracing=bool(settings.otel_endpoint))
    task = asyncio.create_task(_ingest_in_background())
    # MCP: a fresh streamable-HTTP app per lifespan (its session manager can only run once).
    from app.mcp_server import build_mcp_app, mcp

    _mcp_mount.app = build_mcp_app()
    async with mcp.session_manager.run():
        yield
    task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="Veltrix PeopleOps Assistant", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(get_settings().cors_origins),
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Employee-Id", "Authorization"],
    )
    app.include_router(router)
    app.include_router(app_router)
    app.router.routes.append(_mcp_mount)  # /mcp/ — Model Context Protocol endpoint (see app/mcp_server.py)
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
    except Exception:  # pragma: no cover
        log.warning("fastapi_instrumentation_unavailable")
    return app


app = create_app()
