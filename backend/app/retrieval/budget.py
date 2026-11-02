"""Corpus-token budget: at most 3,000 cl100k_base tokens of corpus text per LLM call (TASK 4.3)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import CORPUS_TOKEN_BUDGET
from app.llm.tokens import count_tokens
from app.retrieval.search import Hit

UPCOMING_SHARE = 600  # at most this many tokens of the budget go to not-yet-effective documents


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Evidence:
    evidence_id: str  # E1.. for current, U1.. for upcoming
    hit: Hit
    text: str  # exactly what the LLM sees for this item (header + chunk text)
    tokens: int


@dataclass
class EvidencePack:
    items: list[Evidence] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)  # chunk ids that did not fit

    @property
    def tokens(self) -> int:
        return sum(e.tokens for e in self.items)

    def by_id(self) -> dict[str, Evidence]:
        return {e.evidence_id: e for e in self.items}

    def render(self) -> str:
        return "\n\n".join(e.text for e in self.items)


def _render(evidence_id: str, hit: Hit) -> str:
    d = hit.doc
    status = f"NOT YET EFFECTIVE (from {d.effective_date})" if hit.upcoming else "in effect"
    header = (
        f"[{evidence_id}] doc_id={d.doc_id} | title={d.title} | type={d.doc_type} | "
        f"regions={','.join(d.regions)} | effective={d.effective_date} ({status}) | section={hit.chunk.locator}"
    )
    return f"{header}\n<<<\n{hit.chunk.text}\n>>>"


def pack(current: list[Hit], upcoming: list[Hit], budget: int = CORPUS_TOKEN_BUDGET) -> EvidencePack:
    """Greedy packing in relevance order; every item's full rendered text counts towards the budget."""
    out = EvidencePack()
    used = 0
    seen: set[str] = set()
    n_cur = n_up = 0
    for hit in current:
        if hit.chunk.chunk_id in seen:
            continue
        text = _render(f"E{n_cur + 1}", hit)
        t = count_tokens(text) + 2
        if used + t > budget - (UPCOMING_SHARE if upcoming else 0):
            out.dropped.append(hit.chunk.chunk_id)
            continue
        n_cur += 1
        seen.add(hit.chunk.chunk_id)
        out.items.append(Evidence(f"E{n_cur}", hit, text, t))
        used += t
    for hit in upcoming:
        if hit.chunk.chunk_id in seen:
            continue
        text = _render(f"U{n_up + 1}", hit)
        t = count_tokens(text) + 2
        if used + t > budget:
            out.dropped.append(hit.chunk.chunk_id)
            continue
        n_up += 1
        seen.add(hit.chunk.chunk_id)
        out.items.append(Evidence(f"U{n_up}", hit, text, t))
        used += t
    assert_within_budget(out.tokens)
    return out


def assert_within_budget(corpus_tokens: int, budget: int = CORPUS_TOKEN_BUDGET) -> None:
    if corpus_tokens > budget:
        raise BudgetExceeded(f"corpus tokens {corpus_tokens} exceed budget {budget}")
