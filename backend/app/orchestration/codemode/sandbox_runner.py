"""Code Mode sandbox child process. Standalone: imports only the standard library.

Protocol (one JSON object per line):
  parent -> child   {"code": str, "globals": {...}, "functions": [names]}
  child  -> parent  {"t": "call", "fn": name, "kwargs": {...}}
  parent -> child   {"t": "ret", "value": ...}
  child  -> parent  {"t": "done", "result": ..., "stdout": str} | {"t": "error", "error": str, "stdout": str}

The child has no database handle, no secrets (empty environment) and, on Linux, resource
limits that block file writes, new processes and large memory use. Every API function is a
stub that asks the parent, which enforces permissions with the real requester identity.
"""

import json
import sys

_real_stdout = sys.stdout
_stdin = sys.stdin


def _apply_limits():
    try:
        import os

        if hasattr(os, "getuid") and os.getuid() == 0:  # never run model code as root
            os.setgroups([])
            os.setgid(65534)
            os.setuid(65534)
    except Exception:
        pass
    try:
        import resource  # POSIX only

        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    except Exception:
        pass


def _send(obj):
    _real_stdout.write(json.dumps(obj, default=str) + "\n")
    _real_stdout.flush()


def _make_stub(name):
    def stub(*args, **kwargs):
        if args:
            raise TypeError(f"{name}() takes keyword arguments only, e.g. {name}(employee_id=...)")
        _send({"t": "call", "fn": name, "kwargs": kwargs})
        line = _stdin.readline()
        if not line:
            raise RuntimeError("sandbox parent closed")
        msg = json.loads(line)
        if msg.get("t") == "raise":
            raise RuntimeError(msg.get("error", "call failed"))
        return msg.get("value")

    stub.__name__ = name
    return stub


SAFE = [
    "len", "range", "min", "max", "sum", "sorted", "enumerate", "zip", "abs", "round", "int", "float", "str",
    "bool", "list", "dict", "set", "tuple", "any", "all", "isinstance", "reversed", "Exception", "ValueError",
    "KeyError", "TypeError",
]


def main():
    setup = json.loads(_stdin.readline())
    printed = []

    def _print(*args, **_kw):
        if sum(len(p) for p in printed) < 4000:
            printed.append(" ".join(str(a) for a in args))

    import builtins

    safe_builtins = {name: getattr(builtins, name) for name in SAFE}
    safe_builtins["print"] = _print
    g = {"__builtins__": safe_builtins}
    g.update(setup.get("globals", {}))
    for name in setup.get("functions", []):
        g[name] = _make_stub(name)

    code = compile(setup["code"], "<agent_code>", "exec")
    _apply_limits()
    try:
        exec(code, g)
        _send({"t": "done", "result": g.get("result"), "stdout": "\n".join(printed)})
    except Exception as exc:  # report model-code errors back to the parent
        tb = exc.__traceback__
        line = None
        while tb is not None:
            if tb.tb_frame.f_code.co_filename == "<agent_code>":
                line = tb.tb_lineno
            tb = tb.tb_next
        _send({"t": "error", "error": f"{type(exc).__name__}: {exc}", "line": line, "stdout": "\n".join(printed)})


if __name__ == "__main__":
    main()
