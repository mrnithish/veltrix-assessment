"""Which documents a requester may use (TASK 3.1 + 5.1 rule 1).

This is the single source of truth for document access. The search layer turns
``eligible_doc_ids`` into a vector-store filter, so restricted documents are removed
during retrieval, before anything reaches an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.ingestion.models import DocMeta

ROLE_ACCESS: dict[str, frozenset[str]] = {
    "employee": frozenset({"all"}),
    "manager": frozenset({"all", "managers"}),
    "hr": frozenset({"all", "managers", "hr"}),
}


@dataclass(frozen=True)
class Requester:
    """Identity from the database only (never from the message)."""

    employee_id: str
    role: str
    region: str


def can_read(role: str, access_level: str) -> bool:
    return access_level in ROLE_ACCESS.get(role, frozenset())


def region_matches(doc: DocMeta, region: str) -> bool:
    return "GLOBAL" in doc.regions or region in doc.regions


def is_eligible(doc: DocMeta, requester: Requester, ref_date: date) -> bool:
    return (
        can_read(requester.role, doc.access_level)
        and region_matches(doc, requester.region)
        and doc.effective_date <= ref_date.isoformat()
    )


def is_upcoming(doc: DocMeta, requester: Requester, ref_date: date) -> bool:
    """Readable, for the requester's region, but not yet effective on ref_date."""
    return (
        can_read(requester.role, doc.access_level)
        and region_matches(doc, requester.region)
        and doc.effective_date > ref_date.isoformat()
    )


def eligible_doc_ids(docs: dict[str, DocMeta], requester: Requester, ref_date: date) -> set[str]:
    return {d.doc_id for d in docs.values() if is_eligible(d, requester, ref_date)}


def upcoming_doc_ids(docs: dict[str, DocMeta], requester: Requester, ref_date: date) -> set[str]:
    return {d.doc_id for d in docs.values() if is_upcoming(d, requester, ref_date)}


def readable_doc_ids(docs: dict[str, DocMeta], requester: Requester) -> set[str]:
    return {d.doc_id for d in docs.values() if can_read(requester.role, d.access_level)}


def eligibility_stats(docs: dict[str, DocMeta], requester: Requester, ref_date: date) -> dict:
    """Counts of documents excluded per reason (for traces; no titles or ids of restricted docs)."""
    stats = {"total": len(docs), "eligible": 0, "excluded_access": 0, "excluded_region": 0, "excluded_future": 0}
    for d in docs.values():
        if not can_read(requester.role, d.access_level):
            stats["excluded_access"] += 1
        elif not region_matches(d, requester.region):
            stats["excluded_region"] += 1
        elif d.effective_date > ref_date.isoformat():
            stats["excluded_future"] += 1
        else:
            stats["eligible"] += 1
    return stats
