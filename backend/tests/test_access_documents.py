"""Document access per role: restricted documents never reach retrieval results or the LLM."""

from datetime import date

import pytest

from app.retrieval.eligibility import Requester, can_read, eligible_doc_ids
from app.retrieval.search import search

TODAY = date(2026, 6, 15)


@pytest.mark.parametrize("role,level,allowed", [
    ("employee", "all", True), ("employee", "managers", False), ("employee", "hr", False),
    ("manager", "all", True), ("manager", "managers", True), ("manager", "hr", False),
    ("hr", "all", True), ("hr", "managers", True), ("hr", "hr", True),
])
def test_role_access_matrix(role, level, allowed):
    assert can_read(role, level) is allowed


def test_region_and_date_filters(corpus):
    ids_in = eligible_doc_ids(corpus.docs, Requester("E201", "employee", "IN"), TODAY)
    assert "ADD-VOL-DE" not in ids_in and "CAL-DE-2026" not in ids_in
    assert "POL-VOL-V3" not in ids_in  # not yet effective
    assert "MEMO-SCAN" in ids_in  # regions ["IN", "US"]
    ids_de = eligible_doc_ids(corpus.docs, Requester("E301", "employee", "DE"), TODAY)
    assert "ADD-VOL-DE" in ids_de and "MEMO-SCAN" not in ids_de


@pytest.mark.parametrize("emp,role,expect_mgr,expect_hr", [
    ("E201", "employee", False, False),
    ("E200", "manager", True, False),
    ("E100", "hr", True, True),
])
def test_search_never_returns_unreadable_docs(corpus, emp, role, expect_mgr, expect_hr):
    req = Requester(emp, role, "IN")
    current, upcoming = search(corpus.index, "MANAGERSECRET HRSECRET approval salary band", req, TODAY, k=20)
    docs = {h.doc.doc_id for h in current + upcoming}
    assert ("HB-MGR" in docs) is expect_mgr
    assert ("HR-BANDS" in docs) is expect_hr


def test_upcoming_search_only_for_readable_region_docs(corpus):
    _, upcoming = search(corpus.index, "volunteer days", Requester("E201", "employee", "IN"), TODAY)
    assert {h.doc.doc_id for h in upcoming} <= {"POL-VOL-V3"}


def test_strong_single_retriever_match_is_kept(corpus):
    """A hit in the top results of one retriever is never dropped by rank fusion."""
    from app.retrieval.search import GUARANTEED_PER_RETRIEVER, _search

    req = Requester("E100", "hr", "IN")
    allowed = eligible_doc_ids(corpus.docs, req, TODAY)
    q = "hotel stays reimbursed per night receipts"
    top_lexical = [cid for cid, _ in corpus.index.lexical_search(q, allowed, GUARANTEED_PER_RETRIEVER)]
    kept = [cid for cid, _ in _search(corpus.index, q, allowed, k=4, per_doc=2)]
    assert top_lexical and set(top_lexical[:1]) <= set(kept)
