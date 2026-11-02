"""Live agent events for the streaming endpoint (POST /chat/stream) — the "thinking" view in the UI.

Events are small and contain no personal data: ids, document ids/sections, statuses, counts and
the model-written code. Emitting is thread-safe because Code Mode tool calls run in a worker thread.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.observability.pii import scrub_obj


class EventSink:
    def __init__(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.queue: asyncio.Queue = asyncio.Queue()
        self.t0 = time.perf_counter()

    def emit(self, type_: str, **data: Any) -> None:
        event = {"type": type_, "t_ms": round((time.perf_counter() - self.t0) * 1000), **scrub_obj(data)}
        self.loop.call_soon_threadsafe(self.queue.put_nowait, event)

    def close(self) -> None:
        self.loop.call_soon_threadsafe(self.queue.put_nowait, None)


class NullSink:
    def emit(self, type_: str, **data: Any) -> None:
        return None

    def close(self) -> None:
        return None


NULL_SINK = NullSink()


def summarize_call(fn: str, out: Any) -> str:
    """One short, PII-free line describing a function result."""
    if isinstance(out, dict) and out.get("ok") is False:
        return f"error: {out.get('error', '')}"[:200]
    if fn == "search_policies" and isinstance(out, list):
        docs = list(dict.fromkeys(r["doc_id"] for r in out))
        more = f" +{len(docs) - 4} more" if len(docs) > 4 else ""
        return f"{len(out)} passage(s) from {len(docs)} document(s): " + ", ".join(docs[:4]) + more
    if not isinstance(out, dict):
        return "done"
    if fn == "get_leave_balance":
        return "balances: " + ", ".join(f"{k} {v:g}" for k, v in (out.get("balances") or {}).items())
    if fn == "list_leave_requests":
        return f"{len(out.get('requests') or [])} request(s)"
    if fn == "get_team_leave":
        return f"{len(out.get('team_leave') or [])} overlapping request(s) in the team"
    if fn in ("apply_leave", "cancel_leave"):
        p = out.get("proposal") or {}
        if fn == "apply_leave":
            return f"proposal: {p.get('leave_type')} {p.get('start_date')} → {p.get('end_date')}, " \
                   f"{p.get('working_days')} working day(s) — waiting for confirmation"
        return f"proposal: cancel {p.get('request_id')} — waiting for confirmation"
    if fn == "get_holidays":
        return f"{len(out.get('holidays') or [])} public holiday(s)"
    if fn == "count_working_days":
        return f"{out.get('working_days')} working day(s)"
    if fn == "resolve_dates":
        return out.get("error") or f"{out.get('start_date')} → {out.get('end_date')}"
    if fn == "find_employee":
        return f"{len(out.get('matches') or [])} match(es)"
    return "done"


def instrument(functions: dict, sink) -> dict:
    """Wrap agent functions so each call and its result summary is streamed."""
    if isinstance(sink, NullSink):
        return functions

    def wrap(name, fn):
        def inner(**kwargs):
            sink.emit("call", fn=name, args={k: v for k, v in kwargs.items() if v is not None})
            t0 = time.perf_counter()
            out = fn(**kwargs)
            ok = not (isinstance(out, dict) and out.get("ok") is False)
            sink.emit("call_done", fn=name, ok=ok, summary=summarize_call(name, out),
                      ms=round((time.perf_counter() - t0) * 1000))
            return out
        return inner

    return {name: wrap(name, fn) for name, fn in functions.items()}
