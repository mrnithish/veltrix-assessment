"""Leave-data access rules (TASK 3.1, 6.1, 7.3). Identity always comes from the X-Employee-Id header."""

from __future__ import annotations

from app.data import repositories as repo
from app.data.repositories import Employee

NOT_ALLOWED_MESSAGE = "I can't share information about that employee."
BULK_MESSAGE = "I can't share leave data for several employees at once. Please ask about one employee at a time."
TEAM_ONLY_MANAGERS = "Team leave is only available to managers, for their own direct reports."


def can_view_employee(requester: Employee, target_id: str) -> bool:
    """Self always; managers their direct reports; HR any one existing employee."""
    if not target_id:
        return False
    if target_id == requester.employee_id:
        return True
    target = repo.get_employee(target_id)
    if target is None:
        return False
    if requester.role == "hr":
        return True
    if requester.role == "manager":
        return target.manager_id == requester.employee_id
    return False


def viewable_employees(requester: Employee) -> list[Employee]:
    """Employees whose leave data (and name) the requester may see."""
    if requester.role == "hr":
        return repo.list_employees()
    people = [requester]
    if requester.role == "manager":
        people += [e for e in repo.list_employees() if e.manager_id == requester.employee_id]
    return people
