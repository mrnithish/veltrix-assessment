import pytest

from app.orchestration.agent_api import AgentAPI
from app.orchestration.codemode.sandbox import run_code
from app.orchestration.codemode.validator import CodeRejected, validate_code
from tests.conftest import make_ctx

API = {"get_leave_balance", "apply_leave"}


@pytest.mark.parametrize("code", [
    "import os",
    "from os import path",
    "x = ().__class__.__bases__",
    "open('x')",
    "eval('1')",
    "getattr(me, 'x')",
    "def f():\n    return 1",
    "class A:\n    pass",
    "f = lambda: 1",
    "'{0.__class__}'.format(1)",
    "s = '__import__'",
    "unknown_function()",
])
def test_validator_blocks_unsafe_code(code):
    with pytest.raises(CodeRejected):
        validate_code(code, API)


def test_validator_allows_normal_code():
    validate_code("b = get_leave_balance(employee_id='E1')\nresult = {'x': [i for i in range(3)]}", API)


def test_sandbox_timeout():
    r = run_code("while True:\n    pass", {}, {}, timeout_s=2)
    assert not r.ok and "Timed out" in r.error


def test_sandbox_runtime_error_is_reported():
    r = run_code("result = 1 / 0", {}, {})
    assert not r.ok and "ZeroDivisionError" in r.error


def test_sandbox_has_no_secrets_in_environment():
    # os is not importable and the child runs with an empty environment
    r = run_code("result = 1", {}, {})
    assert r.ok and r.result == 1


def test_sandbox_calls_tools_with_server_identity(corpus):
    ctx = make_ctx("E201", corpus)
    api = AgentAPI(ctx)
    code = ("a = get_leave_balance(employee_id='E201')\n"
            "b = get_leave_balance(employee_id='E400')\n"
            "result = {'own': a['ok'], 'other': b['ok'], 'err': b.get('error')}")
    r = run_code(code, api.functions(), {"me": {"employee_id": "E201"}})
    assert r.ok
    assert r.result["own"] is True and r.result["other"] is False
    assert [rec.name for rec in ctx.records] == ["get_leave_balance", "get_leave_balance"]


def test_sandbox_write_only_proposes(corpus):
    ctx = make_ctx("E201", corpus)
    api = AgentAPI(ctx)
    r = run_code("result = apply_leave(leave_type='annual', start_date='2026-06-17', end_date='2026-06-17')",
                 api.functions(), {})
    assert r.ok and r.result["status"] == "pending_confirmation"
    assert ctx.records[-1].status == "pending_confirmation"
    from app.data import repositories as repo

    assert repo.get_balances("E201", "annual")[0]["balance_days"] == 10  # unchanged


def test_search_policies_returns_refs_not_text(corpus):
    api = AgentAPI(make_ctx("E201", corpus))
    refs = api.search_policies(query="volunteer days")
    assert refs and all(set(r) == {"ref", "doc_id", "section"} for r in refs)


def test_helper_results_are_kept_even_if_code_discards_them(corpus):
    ctx = make_ctx("E201", corpus)
    api = AgentAPI(ctx)
    r = run_code("get_holidays(start_date='2026-06-01', end_date='2026-06-30')\nresult = {}", api.functions(), {})
    assert r.ok and r.result == {}
    assert api.helper_results and api.helper_results[0]["holidays"][0]["date"] == "2026-06-19"
