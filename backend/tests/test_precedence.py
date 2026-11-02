"""TASK 5.2 worked example and the precedence/conflict rules."""

from datetime import date

from app.ingestion.models import DocMeta
from app.retrieval.eligibility import Requester, is_eligible, is_upcoming
from app.retrieval.precedence import Candidate, deciding_test, resolve_rule

V1 = DocMeta("V1", "v1.pdf", "Global policy v1", "policy", ("GLOBAL",), "2025-01-01", "all")
V2 = DocMeta("V2", "v2.pdf", "Global policy v2", "policy", ("GLOBAL",), "2026-04-01", "all")
FAQ = DocMeta("FAQ", "faq.html", "Employee FAQ", "faq", ("GLOBAL",), "2026-05-01", "all")
DE = DocMeta("DE", "de.pdf", "Germany addendum", "addendum", ("DE",), "2025-06-01", "all")
V3 = DocMeta("V3", "v3.docx", "Global policy v3", "policy", ("GLOBAL",), "2027-01-01", "all")
VALUES = {"V1": "2 days", "V2": "3 days", "FAQ": "2 days", "DE": "5 days", "V3": "4 days"}
ALL = [V1, V2, FAQ, DE, V3]


def candidates_for(region: str, ref: date) -> list[Candidate]:
    req = Requester("E1", "employee", region)
    out = []
    for doc in ALL:
        if is_eligible(doc, req, ref):
            out.append(Candidate(doc.doc_id, doc, VALUES[doc.doc_id]))
        elif is_upcoming(doc, req, ref):
            out.append(Candidate(doc.doc_id, doc, VALUES[doc.doc_id], upcoming=True))
    return out


def test_india_today_v2_wins_and_v3_is_upcoming():
    res = resolve_rule("volunteer days", candidates_for("IN", date(2026, 9, 15)))
    assert res.status == "resolved"
    assert [w.doc.doc_id for w in res.winners] == ["V2"]
    assert res.upcoming is not None and res.upcoming.doc.doc_id == "V3"
    overruled = {c.doc.doc_id: why for c, why in res.overruled}
    assert overruled == {"V1": "recency", "FAQ": "authority"}


def test_germany_today_addendum_wins_and_v3_not_mentioned():
    res = resolve_rule("volunteer days", candidates_for("DE", date(2026, 9, 15)))
    assert [w.doc.doc_id for w in res.winners] == ["DE"]
    assert res.winners[0].value == "5 days"
    assert res.upcoming is None  # the addendum would still win on scope in 2027


def test_india_past_date_only_v1_eligible():
    cands = candidates_for("IN", date(2025, 8, 1))
    current = [c.doc.doc_id for c in cands if not c.upcoming]
    assert current == ["V1"]
    res = resolve_rule("volunteer days", [c for c in cands if not c.upcoming])
    assert res.winners[0].value == "2 days"


def test_authority_beats_scope_and_recency():
    wiki_de = DocMeta("W", "w.html", "Wiki", "wiki", ("DE",), "2026-06-01", "all")
    assert deciding_test(V1, wiki_de) == "authority"
    res = resolve_rule("r", [Candidate("a", V1, "1"), Candidate("b", wiki_de, "9")])
    assert res.winners[0].doc.doc_id == "V1"


def test_scope_beats_recency():
    assert deciding_test(DE, V2) == "scope"


def test_unresolved_conflict_returns_both():
    a = DocMeta("A", "a.pdf", "A", "policy", ("GLOBAL",), "2026-01-01", "all")
    b = DocMeta("B", "b.pdf", "B", "handbook", ("GLOBAL",), "2026-01-01", "all")
    res = resolve_rule("r", [Candidate("a", a, "10 days"), Candidate("b", b, "12 days")])
    assert res.status == "conflict"
    assert {w.doc.doc_id for w in res.winners} == {"A", "B"}


def test_same_value_different_wording_is_not_a_conflict():
    a = DocMeta("A", "a.pdf", "A", "policy", ("GLOBAL",), "2026-01-01", "all")
    b = DocMeta("B", "b.pdf", "B", "policy", ("GLOBAL",), "2026-01-01", "all")
    res = resolve_rule("r", [Candidate("a", a, "12 working days"), Candidate("b", b, "12 days")])
    assert res.status == "resolved"


def test_upcoming_not_mentioned_when_value_unchanged():
    res = resolve_rule("r", [Candidate("a", V2, "3 days"), Candidate("u", V3, "3 days", upcoming=True)])
    assert res.upcoming is None


def test_several_values_from_one_document_are_conditions_not_conflict():
    table = DocMeta("T", "t.pdf", "Accrual table", "policy", ("GLOBAL",), "2025-01-01", "all")
    res = resolve_rule("accrual", [Candidate("a", table, "1.5 days/month (<2 years)"),
                                   Candidate("b", table, "1.75 days/month (2 to <5 years)")])
    assert res.status == "resolved" and len(res.winners) == 2


def test_extracted_values_must_be_grounded_in_the_passage():
    from app.orchestration.agent import is_grounded

    passage = "Employees receive 12 working days of paid sick leave in each leave year."
    assert is_grounded("12 working days", passage)
    assert is_grounded("paid sick leave", passage)
    assert not is_grounded("10 days a year", passage)


def test_grounding_checks_main_quantity_only():
    from app.orchestration.agent import is_grounded

    memo = "With effect from 1 July 2026, employees may work from home for up to 3 days per week."
    assert is_grounded("up to 3 days per week (from 2026-07-01)", memo)
    assert not is_grounded("up to 4 days per week", memo)


def test_rule_must_match_passage_topic():
    from app.retrieval.precedence import rule_matches_passage

    notice = "2. Notice periods after probation\n| Level | Notice |\n| L4 to L5 | 60 days |"
    assert not rule_matches_passage("salary bands for L5", notice)
    assert rule_matches_passage("notice period for L5", notice)
    assert rule_matches_passage("carry forward limit", "2. Carrying annual leave forward\nUp to 10 days ...")
    assert rule_matches_passage("the rule", "anything")  # no content words: not checked


def test_no_change_is_not_an_upcoming_change():
    res = resolve_rule("sick days", [Candidate("a", V2, "12 days"),
                                     Candidate("u", V3, "no change from 2027", upcoming=True)])
    assert res.upcoming is None


def test_faq_copy_under_another_rule_name_is_dropped():
    from app.retrieval.precedence import drop_redundant_low_authority

    strong = resolve_rule("sick leave days per year", [Candidate("a", V1, "10 working days")])
    weak = resolve_rule("sick days allowance", [Candidate("b", FAQ, "10 days a year")])
    assert drop_redundant_low_authority([strong, weak]) == [strong]


def test_complementary_statements_are_not_overruled():
    handbook = DocMeta("HB", "hb.pdf", "Manager handbook", "handbook", ("GLOBAL",), "2026-01-01", "managers")
    res = resolve_rule("approving leave", [
        Candidate("a", V2, "Annual leave must be requested in the HR system and approved by the line manager"),
        Candidate("b", handbook, "Respond to every request within 2 working days"),
    ])
    assert {w.doc.doc_id for w in res.winners} == {"V2", "HB"} and not res.overruled
