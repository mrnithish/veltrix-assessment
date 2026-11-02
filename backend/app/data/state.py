"""App-owned tables (sessions, proposals, traces, audit, ingested holidays).

These live in a separate SQLite file (STATE_DB_PATH) so the graders' veltrix.db is only
touched by leave reads/writes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.data.db import state_db, transaction

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  session_id  TEXT PRIMARY KEY,
  employee_id TEXT NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id  TEXT NOT NULL,
  role        TEXT NOT NULL,
  content     TEXT NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
CREATE TABLE IF NOT EXISTS proposals (
  session_id  TEXT PRIMARY KEY,
  payload     TEXT NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_traces (
  request_id  TEXT PRIMARY KEY,
  session_id  TEXT NOT NULL,
  employee_id TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  route       TEXT,
  payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_traces_session ON chat_traces(session_id);
CREATE TABLE IF NOT EXISTS audit_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          TEXT NOT NULL,
  request_id  TEXT,
  employee_id TEXT,
  tool        TEXT NOT NULL,
  args        TEXT NOT NULL,
  status      TEXT NOT NULL,
  detail      TEXT
);
CREATE TABLE IF NOT EXISTS llm_usage (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  ts                TEXT NOT NULL,
  request_id        TEXT,
  employee_id       TEXT,
  provider          TEXT NOT NULL,
  requested_model   TEXT NOT NULL,
  model             TEXT NOT NULL,
  purpose           TEXT NOT NULL,
  prompt_tokens     INTEGER NOT NULL,
  completion_tokens INTEGER NOT NULL,
  corpus_tokens     INTEGER NOT NULL,
  latency_ms        REAL NOT NULL,
  outcome           TEXT NOT NULL,
  error             TEXT,
  attempts          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON llm_usage(ts);
CREATE TABLE IF NOT EXISTS holidays (
  doc_id      TEXT NOT NULL,
  date        TEXT NOT NULL,
  name        TEXT NOT NULL,
  kind        TEXT NOT NULL,
  PRIMARY KEY (doc_id, date, kind)
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def init_state_db() -> None:
    with state_db() as conn:
        conn.executescript(SCHEMA)
        # migration: messages.request_id links a message to its trace (chat history + "thinking" view)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
        if "request_id" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN request_id TEXT")


# ---- sessions -----------------------------------------------------------------

def claim_session(session_id: str, employee_id: str) -> bool:
    """Bind a new session to the employee; return False if it belongs to someone else."""
    with state_db() as conn, transaction(conn):
        row = conn.execute("SELECT employee_id FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO sessions (session_id, employee_id, created_at) VALUES (?, ?, ?)",
                (session_id, employee_id, _now()),
            )
            return True
        return row["employee_id"] == employee_id


def add_message(session_id: str, role: str, content: str, request_id: str | None = None) -> None:
    with state_db() as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at, request_id) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, _now(), request_id),
        )


def list_sessions(employee_id: str, limit: int = 100) -> list[dict]:
    """The employee's conversations, newest first, titled by their first message."""
    with state_db() as conn:
        rows = conn.execute(
            """
            SELECT s.session_id, s.created_at,
                   MAX(m.created_at) AS updated_at,
                   COUNT(m.id) AS message_count,
                   (SELECT content FROM messages f WHERE f.session_id = s.session_id AND f.role = 'user'
                    ORDER BY f.id LIMIT 1) AS title
            FROM sessions s JOIN messages m ON m.session_id = s.session_id
            WHERE s.employee_id = ?
            GROUP BY s.session_id
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (employee_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def session_owner(session_id: str) -> str | None:
    with state_db() as conn:
        row = conn.execute("SELECT employee_id FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    return row["employee_id"] if row else None


def session_messages(session_id: str) -> list[dict]:
    """All messages of a session; assistant messages carry their API response (from the trace)."""
    with state_db() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.role, m.content, m.created_at, m.request_id, t.payload
            FROM messages m LEFT JOIN chat_traces t ON t.request_id = m.request_id AND m.role = 'assistant'
            WHERE m.session_id = ? ORDER BY m.id
            """,
            (session_id,),
        ).fetchall()
    out = []
    for r in rows:
        item = {"id": r["id"], "role": r["role"], "content": r["content"], "created_at": r["created_at"],
                "request_id": r["request_id"]}
        if r["payload"]:
            item["response"] = json.loads(r["payload"]).get("response")
        out.append(item)
    return out


def delete_session(session_id: str) -> None:
    """Remove a conversation from history. Traces and audit events are kept for traceability."""
    with state_db() as conn, transaction(conn):
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM proposals WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


def recent_messages(session_id: str, limit: int = 8) -> list[dict]:
    with state_db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


# ---- proposals (at most one per session) -------------------------------------------

def set_proposal(session_id: str, payload: dict) -> None:
    with state_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO proposals (session_id, payload, created_at) VALUES (?, ?, ?)",
            (session_id, json.dumps(payload), _now()),
        )


def get_proposal(session_id: str) -> dict | None:
    with state_db() as conn:
        row = conn.execute("SELECT payload FROM proposals WHERE session_id = ?", (session_id,)).fetchone()
    return json.loads(row["payload"]) if row else None


def clear_proposal(session_id: str) -> None:
    with state_db() as conn:
        conn.execute("DELETE FROM proposals WHERE session_id = ?", (session_id,))


# ---- traces & audit ---------------------------------------------------------------

def save_trace(request_id: str, session_id: str, employee_id: str, route: str, payload: dict) -> None:
    with state_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO chat_traces (request_id, session_id, employee_id, created_at, route, payload) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (request_id, session_id, employee_id, _now(), route, json.dumps(payload, default=str)),
        )


def get_trace(request_id: str) -> dict | None:
    with state_db() as conn:
        row = conn.execute("SELECT * FROM chat_traces WHERE request_id = ?", (request_id,)).fetchone()
    if not row:
        return None
    out = dict(row)
    out["payload"] = json.loads(out["payload"])
    return out


def write_audit(request_id: str | None, employee_id: str | None, tool: str, args: dict, status: str,
                detail: str | None) -> None:
    with state_db() as conn:
        conn.execute(
            "INSERT INTO audit_events (ts, request_id, employee_id, tool, args, status, detail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), request_id, employee_id, tool, json.dumps(args, default=str), status, detail),
        )


# ---- holidays (extracted automatically at ingestion) ------------------------------------

def replace_holidays(rows: list[dict]) -> None:
    with state_db() as conn, transaction(conn):
        conn.execute("DELETE FROM holidays")
        conn.executemany(
            "INSERT OR REPLACE INTO holidays (doc_id, date, name, kind) VALUES (:doc_id, :date, :name, :kind)",
            rows,
        )


def holidays_for_doc(doc_id: str, kind: str = "public") -> list[dict]:
    with state_db() as conn:
        rows = conn.execute(
            "SELECT date, name, kind FROM holidays WHERE doc_id = ? AND kind = ? ORDER BY date", (doc_id, kind)
        ).fetchall()
    return [dict(r) for r in rows]


# ---- LLM usage (token consumption) ---------------------------------------------------------------

def record_llm_usage(row: dict) -> None:
    with state_db() as conn:
        conn.execute(
            "INSERT INTO llm_usage (ts, request_id, employee_id, provider, requested_model, model, purpose, "
            "prompt_tokens, completion_tokens, corpus_tokens, latency_ms, outcome, error, attempts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_now(), row.get("request_id"), row.get("employee_id"), row["provider"], row["requested_model"],
             row["model"], row["purpose"], int(row["prompt_tokens"]), int(row["completion_tokens"]),
             int(row["corpus_tokens"]), float(row["latency_ms"]), row["outcome"], row.get("error"),
             json.dumps(row.get("attempts") or [])),
        )


_USAGE_QUERIES = {
    "totals": """SELECT COUNT(*) AS calls, COUNT(DISTINCT request_id) AS requests,
        COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens, COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
        COALESCE(SUM(corpus_tokens), 0) AS corpus_tokens, COALESCE(MAX(corpus_tokens), 0) AS max_corpus_tokens,
        COALESCE(ROUND(AVG(latency_ms)), 0) AS avg_latency_ms,
        COALESCE(SUM(CASE WHEN outcome != 'ok' THEN 1 ELSE 0 END), 0) AS errors,
        COALESCE(SUM(CASE WHEN model != requested_model THEN 1 ELSE 0 END), 0) AS fallbacks
        FROM llm_usage WHERE {where}""",
    "by_purpose": """SELECT purpose, COUNT(*) AS calls, SUM(prompt_tokens) AS prompt_tokens,
        SUM(completion_tokens) AS completion_tokens, ROUND(AVG(corpus_tokens)) AS avg_corpus_tokens,
        MAX(corpus_tokens) AS max_corpus_tokens, ROUND(AVG(latency_ms)) AS avg_latency_ms
        FROM llm_usage WHERE {where} GROUP BY purpose ORDER BY calls DESC""",
    "by_model": """SELECT provider, model, COUNT(*) AS calls, SUM(prompt_tokens + completion_tokens) AS tokens,
        ROUND(AVG(latency_ms)) AS avg_latency_ms, SUM(CASE WHEN outcome != 'ok' THEN 1 ELSE 0 END) AS errors
        FROM llm_usage WHERE {where} GROUP BY provider, model ORDER BY calls DESC""",
    "by_day": """SELECT substr(ts, 1, 10) AS day, COUNT(*) AS calls, SUM(prompt_tokens) AS prompt_tokens,
        SUM(completion_tokens) AS completion_tokens, SUM(corpus_tokens) AS corpus_tokens
        FROM llm_usage WHERE {where} GROUP BY day ORDER BY day""",
    "corpus_budget": """SELECT CASE WHEN corpus_tokens = 0 THEN '0' WHEN corpus_tokens <= 1000 THEN '1-1000'
        WHEN corpus_tokens <= 2000 THEN '1001-2000' ELSE '2001-3000' END AS bucket, COUNT(*) AS calls
        FROM llm_usage WHERE {where} GROUP BY bucket ORDER BY bucket""",
    "recent": """SELECT ts, request_id, provider, requested_model, model, purpose, prompt_tokens, completion_tokens,
        corpus_tokens, latency_ms, outcome, attempts FROM llm_usage WHERE {where} ORDER BY id DESC LIMIT 25""",
}


def usage_summary(days: int = 14, employee_id: str | None = None) -> dict:
    """Token consumption and reliability aggregates, optionally for one employee."""
    where = "ts >= datetime('now', ?)"
    params: list = [f"-{int(days)} days"]
    if employee_id:
        where += " AND employee_id = ?"
        params.append(employee_id)
    out: dict = {"days": days}
    with state_db() as conn:
        for key, sql in _USAGE_QUERIES.items():
            rows = [dict(r) for r in conn.execute(sql.format(where=where), params).fetchall()]
            out[key] = rows[0] if key == "totals" else rows
    for r in out["recent"]:
        r["attempts"] = json.loads(r["attempts"] or "[]")
    return out
