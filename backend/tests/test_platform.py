"""MCP server, token-usage accounting, model catalog, time/profile awareness."""

from __future__ import annotations

import json

from tests.test_chat_api import VOL_PLAN, VOLUNTEER, Script, client, code, use  # noqa: F401

MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def token_for(c, ident):
    return c.post("/auth/login", json={"identifier": ident, "password": "veltrix"}).json()["token"]


def mcp_call(c, method, params=None, token=None, id_=1):
    headers = dict(MCP_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = c.post("/mcp/", headers=headers, json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})
    assert r.status_code == 200, r.text
    return r.json()


def tool(c, name, args, token):
    res = mcp_call(c, "tools/call", {"name": name, "arguments": args}, token)["result"]
    text = res["content"][0]["text"] if res.get("content") else "{}"
    return res.get("isError", False), (json.loads(text) if text.strip().startswith("{") else text)


# ---------------------------------------------------------------- MCP

def test_mcp_lists_tools(client):
    init = mcp_call(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                           "clientInfo": {"name": "pytest", "version": "1"}})
    assert init["result"]["serverInfo"]["name"] == "veltrix-peopleops"
    names = {t["name"] for t in mcp_call(client, "tools/list")["result"]["tools"]}
    assert {"whoami", "ask_hr_assistant", "get_leave_balance", "list_leave_requests", "get_team_leave",
            "list_holidays", "list_documents", "search_hr_documents"} <= names


def test_mcp_requires_a_valid_token(client):
    is_error, out = tool(client, "whoami", {}, None)
    assert is_error and "token" in str(out).lower()
    is_error, _ = tool(client, "whoami", {}, "not-a-token")
    assert is_error


def test_mcp_tools_apply_the_same_access_rules(client):
    t = token_for(client, "E201")
    _, me = tool(client, "whoami", {}, t)
    assert me["employee_id"] == "E201" and me["email"] == "p***@veltrix.example" and "phone" not in me
    _, own = tool(client, "get_leave_balance", {}, t)
    assert own["status"] == "success" and own["balances"]["annual"] == 10.0
    _, other = tool(client, "get_leave_balance", {"employee_id": "E400"}, t)
    assert other["status"] == "error" and other["error"] == "I can't share information about that employee."
    _, team = tool(client, "get_team_leave", {"start_date": "2026-07-01", "end_date": "2026-08-31"}, t)
    assert team["status"] == "error"
    _, docs = tool(client, "list_documents", {}, t)
    ids = {d["doc_id"] for d in docs["documents"]}
    assert "HB-MGR" not in ids and "HR-BANDS" not in ids
    _, found = tool(client, "search_hr_documents", {"query": "MANAGERSECRET HRSECRET approval salary"}, t)
    assert all(r["doc_id"] not in ("HB-MGR", "HR-BANDS") for r in found["results"])
    _, hol = tool(client, "list_holidays", {"year": 2026}, t)
    assert hol["calendar"]["doc_id"] == "CAL-IN-2026"


def test_mcp_ask_hr_assistant_keeps_session_and_confirmation(client):
    use(Script({"annual leave": code("result = apply_leave(leave_type='annual', start_date='2026-06-17', "
                                     "end_date='2026-06-18')")}))
    t = token_for(client, "E201")
    _, first = tool(client, "ask_hr_assistant", {"message": "Book annual leave 17-18 June"}, t)
    assert first["pending_confirmation"] is True and first["route"] == "tool"
    _, done = tool(client, "ask_hr_assistant", {"message": "yes", "session_id": first["session_id"]}, t)
    assert done["tool_calls"][0]["status"] == "success"
    other = token_for(client, "E202")
    is_error, _ = tool(client, "ask_hr_assistant", {"message": "yes", "session_id": first["session_id"]}, other)
    assert is_error


def test_mcp_token_endpoint_returns_client_configs(client):
    t = token_for(client, "E201")
    out = client.post("/me/mcp-token", headers={"Authorization": f"Bearer {t}"}).json()
    assert out["url"].endswith("/mcp/") and out["token"]
    assert out["configs"]["cursor"]["mcpServers"]["veltrix"]["headers"]["Authorization"].startswith("Bearer ")
    _, me = tool(client, "whoami", {}, out["token"])
    assert me["employee_id"] == "E201"


# ---------------------------------------------------------------- usage, catalog, time, profile

def test_usage_records_every_llm_call(client):
    use(Script(VOL_PLAN, VOLUNTEER))
    client.post("/chat", headers={"X-Employee-Id": "E201"},
                json={"session_id": "usage-1", "message": "How many volunteer days do I get?"})
    t = token_for(client, "E201")
    u = client.get("/usage", headers={"Authorization": f"Bearer {t}"}).json()
    assert u["totals"]["calls"] >= 3 and u["totals"]["max_corpus_tokens"] <= 3000
    assert {"plan", "extract", "compose"} <= {p["purpose"] for p in u["by_purpose"]}
    assert u["mine"]["calls"] >= 3
    assert all("employee_id" not in r for r in u["recent"])


def test_model_catalog_includes_gpt_oss(client):
    nv = client.get("/llm/models?provider=nvidia").json()
    ids = {m["id"] for m in nv["models"]}
    assert "openai/gpt-oss-120b" in ids and "nvidia/nemotron-3.5-lightning-30b-a3b" in ids
    ol = client.get("/llm/models?provider=ollama").json()
    assert "gpt-oss:120b" in {m["id"] for m in ol["models"]}


def test_me_has_current_time_and_timezone(client):
    t = token_for(client, "E201")
    me = client.get("/me", headers={"Authorization": f"Bearer {t}"}).json()
    assert me["today"] == "2026-06-15" and me["now"].startswith("2026-06-15T") and me["timezone"]


def test_planner_knows_who_is_signed_in(client):
    fake = use(Script({}))
    client.post("/chat", headers={"X-Employee-Id": "E200"}, json={"session_id": "who-1", "message": "hello"})
    system = fake.calls[0][0]["content"]
    assert "employee_id: E200" in system and "direct_reports: E201, E202" in system
    assert "joined: 2017-05-01" in system and "current time:" in system
    assert "Manoj" not in system  # no names in the planner prompt


def test_who_am_i_is_answered_from_the_profile(client):
    use(Script({"who am i": code("p = get_my_profile()\nresult = {'manager': p['manager_id'], "
                                 "'reports': [r['employee_id'] for r in p['direct_reports']]}")},
               compose="You are E200, a manager. Your reports are E201 and E202."))
    body = client.post("/chat", headers={"X-Employee-Id": "E200"},
                       json={"session_id": "who-2", "message": "Who am I and who reports to me?"}).json()
    assert body["route"] == "clarify" and "E201" in body["answer"]
    assert body["tool_calls"] == [] and body["citations"] == []
