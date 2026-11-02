"""JSON schemas for AGENT_MODE=tools (classic function calling)."""


def _fn(name: str, description: str, props: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": props, "required": required, "additionalProperties": False},
    }}


_S = {"type": "string"}
_DATE = {"type": "string", "description": "YYYY-MM-DD"}
_LEAVE = {"type": "string", "enum": ["annual", "sick"]}

TOOL_SCHEMAS = [
    _fn("get_leave_balance", "Current remaining leave balance of one employee.",
        {"employee_id": _S, "leave_type": _LEAVE}, ["employee_id"]),
    _fn("list_leave_requests", "Leave requests of one employee.",
        {"employee_id": _S, "status": {"type": "string", "enum": ["pending", "approved", "cancelled"]}},
        ["employee_id"]),
    _fn("get_team_leave", "Managers only: direct reports' pending/approved leave overlapping a date range.",
        {"start_date": _DATE, "end_date": _DATE}, ["start_date", "end_date"]),
    _fn("apply_leave", "Validate and PROPOSE a leave request for the requester (user confirms later).",
        {"leave_type": _LEAVE, "start_date": _DATE, "end_date": _DATE}, ["leave_type", "start_date", "end_date"]),
    _fn("cancel_leave", "Validate and PROPOSE cancelling one of the requester's own requests.",
        {"request_id": _S}, ["request_id"]),
    _fn("search_policies", "Find HR document passages that apply to the requester; they are attached to the answer.",
        {"query": _S, "as_of": {"type": "string", "description": "YYYY-MM-DD, only for questions about a past date"}},
        ["query"]),
    _fn("get_holidays", "Public holidays for the requester's office in a date range.",
        {"start_date": _DATE, "end_date": _DATE}, ["start_date", "end_date"]),
    _fn("count_working_days", "Working days in a date range for the requester's office.",
        {"start_date": _DATE, "end_date": _DATE}, ["start_date", "end_date"]),
    _fn("resolve_dates", "Turn a relative date phrase into dates.", {"phrase": _S}, ["phrase"]),
    _fn("find_employee", "Find an employee the requester may view, by name.", {"name": _S}, ["name"]),
    _fn("get_my_profile", "The signed-in requester's own profile (role, region, level, manager, team).", {}, []),
    _fn("ask_clarification", "Ask the user for missing information (everything at once).", {"message": _S},
        ["message"]),
    _fn("refuse", "Refuse the request.",
        {"reason": {"type": "string", "enum": ["off_topic", "manipulation", "bulk", "not_permitted"]}}, ["reason"]),
]
