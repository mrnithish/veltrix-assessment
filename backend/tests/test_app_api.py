"""UI endpoints: login, profile, dashboards, chat history and the streaming chat."""

from __future__ import annotations

import json

from tests.test_chat_api import VOL_PLAN, VOLUNTEER, Script, client, code, use  # noqa: F401


def login(c, ident="E201", password="veltrix"):
    r = c.post("/auth/login", json={"identifier": ident, "password": password})
    return r


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_by_id_or_email_and_profile(client):
    r = login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["profile"]["employee_id"] == "E201" and body["profile"]["full_name"] == "Priya Nair"
    assert body["profile"]["email"] == "p***@veltrix.example" and "phone" not in body["profile"]
    assert login(client, "priya.nair@veltrix.example").status_code == 200
    assert login(client, "E201", "wrong").status_code == 401
    assert login(client, "E999").status_code == 401
    assert client.get("/me", headers=auth(body["token"])).json()["employee_id"] == "E201"
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers=auth(body["token"] + "x")).status_code == 401


def test_demo_accounts_have_no_personal_data(client):
    rows = client.get("/auth/demo-accounts").json()
    assert rows and all(set(r) == {"employee_id", "role", "region", "level", "direct_reports"} for r in rows)


def test_my_leave_and_documents_respect_access(client):
    token = login(client).json()["token"]
    leave = client.get("/me/leave", headers=auth(token)).json()
    assert leave["balances"] == {"annual": 10.0, "sick": 8.0}
    assert {r["request_id"] for r in leave["requests"] if r["cancellable"]} == {"req-e201-jul", "req-e201-aug"}
    docs = {d["doc_id"]: d for d in client.get("/me/documents", headers=auth(token)).json()["documents"]}
    assert "HB-MGR" not in docs and "HR-BANDS" not in docs and "ADD-VOL-DE" not in docs
    assert docs["POL-VOL-V3"]["status"] == "upcoming" and docs["POL-VOL-V2"]["status"] == "in_effect"


def test_holidays_from_applicable_calendar(client):
    token = login(client).json()["token"]
    h = client.get("/me/holidays?year=2026", headers=auth(token)).json()
    assert h["calendar"]["doc_id"] == "CAL-IN-2026"
    assert ("2026-06-19", "public") in {(x["date"], x["kind"]) for x in h["holidays"]}


def test_team_views_are_manager_only_and_one_person_at_a_time(client):
    emp = login(client).json()["token"]
    assert client.get("/me/team", headers=auth(emp)).status_code == 403
    mgr = login(client, "E200").json()["token"]
    team = client.get("/me/team?start=2026-07-01&end=2026-08-31", headers=auth(mgr)).json()
    assert {r["employee_id"] for r in team["team"]} == {"E201", "E202"}
    assert {r["request_id"] for r in team["leave"]} == {"req-e201-jul", "req-e201-aug"}
    assert client.get("/me/team/E201/leave", headers=auth(mgr)).json()["balances"]["annual"] == 10.0
    assert client.get("/me/team/E301/leave", headers=auth(mgr)).status_code == 403


def test_chat_history_is_private_and_deletable(client):
    use(Script(VOL_PLAN, VOLUNTEER))
    client.post("/chat", headers={"X-Employee-Id": "E201"},
                json={"session_id": "hist-1", "message": "How many volunteer days do I get?"})
    token = login(client).json()["token"]
    sessions = client.get("/sessions", headers=auth(token)).json()
    assert sessions[0]["session_id"] == "hist-1" and sessions[0]["title"].startswith("How many volunteer")
    msgs = client.get("/sessions/hist-1/messages", headers=auth(token)).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["response"]["route"] == "rag" and msgs[1]["request_id"]
    other = login(client, "E202").json()["token"]
    assert client.get("/sessions/hist-1/messages", headers=auth(other)).status_code == 404
    assert client.delete("/sessions/hist-1", headers=auth(token)).status_code == 200
    assert client.get("/sessions", headers=auth(token)).json() == []


def test_chat_stream_emits_thinking_and_the_same_final_response(client):
    plan = {"volunteer": code("b = get_leave_balance(employee_id=me['employee_id'])\n"
                              "search_policies(query='volunteer days')\nresult = {'b': b}")}
    use(Script(plan, VOLUNTEER))
    r = client.post("/chat/stream", headers={"X-Employee-Id": "E201"},
                    json={"session_id": "stream-1", "message": "My balance and volunteer days?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    types = [e["type"] for e in events]
    for t in ("start", "plan", "call", "call_done", "sandbox", "llm", "evidence", "resolution", "final"):
        assert t in types, t
    plan_event = next(e for e in events if e["type"] == "plan")
    assert "search_policies" in plan_event["code"]
    final = events[-1]
    assert final["type"] == "final" and final["response"]["route"] == "hybrid"
    assert set(final["response"]) == {"request_id", "answer", "route", "citations", "tool_calls",
                                      "pending_confirmation"}


def test_chat_stream_validates_like_chat(client):
    use(Script({}))
    assert client.post("/chat/stream", json={"session_id": "x", "message": "hi"}).status_code == 401
    assert client.post("/chat/stream", headers={"X-Employee-Id": "E201"}, content=b"{").status_code == 400
