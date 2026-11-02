"""Precedence between eligible documents that state different values for the same rule (TASK 5.1).

Tests, in order: authority, then scope, then recency. If all three tie and the values
differ, the conflict is unresolved and both values are reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ingestion.models import DocMeta

AUTHORITATIVE_TYPES = frozenset({"policy", "addendum", "memo", "handbook", "calendar"})
_NO_CHANGE = re.compile(r"\b(no change|unchanged|remains the same|stays the same)\b", re.I)
_RULE_STOP = frozenset(
    ["the", "a", "an", "of", "for", "in", "on", "to", "and", "or", "per", "by", "with", "from", "at", "as", "is", "are", "my", "your", "their", "our", "rule", "value", "values", "number", "amount", "many", "much", "how", "what", "which", "when", "allowance", "entitlement", "leave", "days", "day", "year", "years", "month", "months", "week", "weeks", "employee", "employees", "policy", "limit", "rate", "total", "maximum", "minimum"]
)


def rule_terms(rule: str) -> list[str]:
    """Content words of a rule name, cut to 5 letters so 'carry'/'carrying' or 'band'/'bands' match."""
    return [w[:5] for w in re.findall(r"[a-z]+", rule.lower()) if len(w) >= 4 and w not in _RULE_STOP]


def rule_matches_passage(rule: str, passage: str) -> bool:
    """The passage must mention the rule's subject (e.g. a notice-period table cannot answer 'salary bands')."""
    terms = rule_terms(rule)
    if not terms:
        return True
    words = {w[:5] for w in re.findall(r"[a-z]+", passage.lower())}
    return any(t in words for t in terms)


_WORDS = re.compile(r"[a-z]{3,}")
_NUMS = re.compile(r"\d+(?:\.\d+)?")


def comparable(a: str, b: str) -> bool:
    """Two values compete for the same rule if both state a quantity, or if they are about the same thing."""
    if _NUMS.search(a or "") and _NUMS.search(b or ""):
        return True
    wa, wb = set(_WORDS.findall((a or "").lower())), set(_WORDS.findall((b or "").lower()))
    if not wa or not wb:
        return True
    return len(wa & wb) / len(wa | wb) >= 0.3


def drop_redundant_low_authority(resolutions: list[Resolution]) -> list[Resolution]:
    """Remove a fact answered only by FAQ/wiki when an authoritative fact already gives the same value.

    The extractor sometimes files the FAQ's copy of a rule under a differently-worded rule name; precedence
    (authority) means it must not be cited separately.
    """
    def is_low(r: Resolution) -> bool:
        return bool(r.winners) and all(precedence_key(w.doc)[0] == 0 for w in r.winners)

    strong_values = {normalize_value(w.value) for r in resolutions if not is_low(r) for w in r.winners}
    return [r for r in resolutions
            if not (is_low(r) and all(normalize_value(w.value) in strong_values for w in r.winners))]


def precedence_key(doc: DocMeta) -> tuple[int, int, str]:
    authority = 1 if doc.doc_type in AUTHORITATIVE_TYPES else 0
    scope = 0 if doc.is_global else 1
    return (authority, scope, doc.effective_date)


def deciding_test(a: DocMeta, b: DocMeta) -> str | None:
    """Name of the first test that separates a and b, or None if they tie on all three."""
    ka, kb = precedence_key(a), precedence_key(b)
    for name, x, y in zip(("authority", "scope", "recency"), ka, kb):
        if x != y:
            return name
    return None


def normalize_value(value: str) -> str:
    """Compare values by their numbers when they have any ("12 working days" == "12 days")."""
    text = (value or "").strip().lower()
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    if numbers:
        return "#" + ",".join(str(float(n)) for n in numbers)
    return re.sub(r"[^a-z]+", " ", text).strip()


@dataclass
class Candidate:
    evidence_id: str
    doc: DocMeta
    value: str
    locator: str = ""
    upcoming: bool = False


@dataclass
class Resolution:
    rule: str
    status: str  # "resolved" | "conflict" | "unanswered"
    winners: list[Candidate] = field(default_factory=list)
    overruled: list[tuple[Candidate, str]] = field(default_factory=list)  # (candidate, test that beat it)
    upcoming: Candidate | None = None

    def to_trace(self) -> dict:
        return {
            "rule": self.rule,
            "status": self.status,
            "winners": [(c.doc.doc_id, c.value) for c in self.winners],
            "overruled": [(c.doc.doc_id, c.value, why) for c, why in self.overruled],
            "upcoming": (self.upcoming.doc.doc_id, self.upcoming.value, self.upcoming.doc.effective_date)
            if self.upcoming else None,
        }


def resolve_rule(rule: str, candidates: list[Candidate]) -> Resolution:
    current = [c for c in candidates if not c.upcoming]
    future = [c for c in candidates if c.upcoming]
    res = Resolution(rule=rule, status="unanswered")
    if current:
        best_key = max(precedence_key(c.doc) for c in current)
        top = [c for c in current if precedence_key(c.doc) == best_key]
        # Conflict = documents in the top tier disagree. Several values from ONE document are
        # values for different conditions (e.g. an accrual table by length of service), not a conflict.
        per_doc: dict[str, frozenset[str]] = {}
        for c in top:
            per_doc[c.doc.doc_id] = per_doc.get(c.doc.doc_id, frozenset()) | {normalize_value(c.value)}
        res.status = "conflict" if len(per_doc) > 1 and len(set(per_doc.values())) > 1 else "resolved"
        # One candidate per distinct (doc, value) among the top tier.
        seen: set[tuple[str, str]] = set()
        for c in top:
            key = (c.doc.doc_id, normalize_value(c.value))
            if key not in seen:
                seen.add(key)
                res.winners.append(c)
        for c in current:
            if c in top:
                continue
            if not any(comparable(c.value, w.value) for w in top):
                # A different statement filed under the same rule name (e.g. how managers approve vs how
                # employees request): not a competing value, so both are kept (TASK 5: precedence applies to
                # "different values for the same rule").
                res.winners.append(c)
                continue
            res.overruled.append((c, deciding_test(top[0].doc, c.doc) or "tie"))
    # Upcoming change: the future document must win against the current winner on its effective date
    # (and actually change the value).
    future = [c for c in future if not _NO_CHANGE.search(c.value)]
    if future:
        best_future = max(future, key=lambda c: precedence_key(c.doc))
        if not res.winners:
            res.upcoming = best_future
        else:
            beats_all = all(precedence_key(best_future.doc) > precedence_key(w.doc) for w in res.winners)
            changes = all(normalize_value(best_future.value) != normalize_value(w.value) for w in res.winners)
            if beats_all and changes:
                res.upcoming = best_future
    return res
