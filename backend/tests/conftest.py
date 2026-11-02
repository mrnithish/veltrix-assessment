"""Test fixtures: a small synthetic corpus + database built in a temp dir.

Tests never depend on ./data, because graders replace it with their own copy.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="veltrix-tests-"))
CORPUS = TMP / "corpus"
DB_TEMPLATE = TMP / "template.db"
TODAY = "2026-06-15"  # a Monday

os.environ.update({
    "CORPUS_DIR": str(CORPUS),
    "MANIFEST_PATH": str(TMP / "manifest.json"),
    "DB_PATH": str(TMP / "veltrix.db"),
    "STATE_DB_PATH": str(TMP / "state.db"),
    "EMBEDDING_BACKEND": "hash",
    "LLM_PROVIDER": "fake",
    "APP_TODAY": TODAY,
    "QDRANT_URL": "",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "",
    "LOG_LEVEL": "WARNING",
    "AGENT_MODE": "codemode",
    "DEV_ENDPOINTS": "true",
})

from tests import fixtures_builder

fixtures_builder.build_corpus(CORPUS, TMP / "manifest.json")
fixtures_builder.build_db(DB_TEMPLATE)


@pytest.fixture(autouse=True)
def fresh_databases(monkeypatch):
    """Every test starts from the same HR database and an empty app-state database."""
    monkeypatch.setenv("APP_TODAY", TODAY)
    shutil.copy(DB_TEMPLATE, TMP / "veltrix.db")
    from app.data.state import SCHEMA, init_state_db

    init_state_db()
    conn = sqlite3.connect(TMP / "state.db")
    for table in ("sessions", "messages", "proposals", "chat_traces", "audit_events"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()
    assert SCHEMA
    yield


@pytest.fixture(scope="session")
def corpus():
    from app.config import get_settings
    from app.data import repositories as repo
    from app.data.state import init_state_db
    from app.ingestion.pipeline import run_ingestion, set_corpus
    from app.observability.pii import register_people

    shutil.copy(DB_TEMPLATE, TMP / "veltrix.db")
    init_state_db()
    register_people(repo.list_employees())
    c = run_ingestion(get_settings())
    set_corpus(c)
    return c


def make_ctx(employee_id: str, corpus, request_id: str = "test-req"):
    from app.config import today
    from app.data import repositories as repo
    from app.tools.leave_tools import ToolContext

    return ToolContext(repo.get_employee(employee_id), request_id, today(), corpus)
