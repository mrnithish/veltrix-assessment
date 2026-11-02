"""Parent side of the Code Mode sandbox: validate, spawn the child, serve its API calls."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.observability import metrics
from app.orchestration.codemode.validator import CodeRejected, validate_code

RUNNER = Path(__file__).with_name("sandbox_runner.py")
MAX_CALLS = 25


@dataclass
class SandboxResult:
    ok: bool
    result: Any = None
    stdout: str = ""
    error: str | None = None
    calls: list[dict] = field(default_factory=list)  # [{"fn", "kwargs"}] in order
    duration_ms: float = 0.0


def _child_env() -> dict:
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"}
    if os.name == "nt":  # Windows needs these to start Python at all
        for key in ("SYSTEMROOT", "SystemRoot", "TEMP", "TMP"):
            if key in os.environ:
                env[key] = os.environ[key]
    return env


def run_code(
    code: str,
    functions: dict[str, Callable[..., Any]],
    sandbox_globals: dict,
    timeout_s: float = 8.0,
) -> SandboxResult:
    t0 = time.perf_counter()
    try:
        validate_code(code, set(functions) | set(sandbox_globals) | {"result"})
    except CodeRejected as exc:
        metrics.SANDBOX_RUNS.labels("rejected").inc()
        return SandboxResult(False, error=f"Code rejected: {exc}")

    proc = subprocess.Popen(
        [sys.executable, "-I", "-S", str(RUNNER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=_child_env(),
        cwd=str(RUNNER.parent),
    )
    timed_out = threading.Event()

    def _kill():
        timed_out.set()
        proc.kill()

    timer = threading.Timer(timeout_s, _kill)
    timer.start()
    result = SandboxResult(False)
    try:
        proc.stdin.write(json.dumps({"code": code, "globals": sandbox_globals, "functions": sorted(functions)}) + "\n")
        proc.stdin.flush()
        while True:
            line = proc.stdout.readline()
            if not line:
                result.error = "Timed out" if timed_out.is_set() else "Sandbox exited unexpectedly"
                break
            msg = json.loads(line)
            if msg.get("t") == "call":
                name, kwargs = msg.get("fn"), msg.get("kwargs") or {}
                result.calls.append({"fn": name, "kwargs": kwargs})
                if len(result.calls) > MAX_CALLS:
                    reply = {"t": "raise", "error": f"too many API calls (max {MAX_CALLS})"}
                elif name not in functions:
                    reply = {"t": "raise", "error": f"unknown function {name}"}
                else:
                    try:
                        value = functions[name](**kwargs)
                        reply = {"t": "ret", "value": value}
                    except TypeError as exc:
                        reply = {"t": "raise", "error": f"bad arguments for {name}: {exc}"}
                proc.stdin.write(json.dumps(reply, default=str) + "\n")
                proc.stdin.flush()
            elif msg.get("t") == "done":
                result = SandboxResult(True, msg.get("result"), msg.get("stdout", ""), None, result.calls)
                break
            elif msg.get("t") == "error":
                line_no = msg.get("line")
                where = f" (line {line_no})" if line_no else ""
                result = SandboxResult(False, None, msg.get("stdout", ""), msg.get("error", "") + where, result.calls)
                break
    except (BrokenPipeError, OSError, json.JSONDecodeError) as exc:
        result.error = "Timed out" if timed_out.is_set() else f"Sandbox failure: {exc}"
    finally:
        timer.cancel()
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.communicate(timeout=1)
        except Exception:
            pass
    result.duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    metrics.SANDBOX_RUNS.labels("ok" if result.ok else "error").inc()
    return result
