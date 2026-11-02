"""Hybrid retrieval (dense + BM25, reciprocal-rank fusion) over eligible documents only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.ingestion.models import Chunk, DocMeta
from app.retrieval.eligibility import Requester, eligible_doc_ids, upcoming_doc_ids
from app.retrieval.index import CorpusIndex

RRF_K = 60


@dataclass
class Hit:
    chunk: Chunk
    doc: DocMeta
    score: float
    upcoming: bool = False
    ref_date: str = ""


def _fuse(*rankings: list[tuple[str, float]]) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, (cid, _s) in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    return sorted(scores.items(), key=lambda kv: -kv[1])


GUARANTEED_PER_RETRIEVER = 3


def _search(index: CorpusIndex, query: str, allowed: set[str], k: int, per_doc: int) -> list[tuple[str, float]]:
    """Top hits of EACH retriever are kept first, then the rest is filled by fused rank.

    Plain RRF can bury a strong match that only one retriever finds (e.g. an OCR'd memo whose
    embedding is diluted by header/signature text but which matches every query word).
    """
    dense = index.dense_search(query, allowed, limit=k * 3)
    lexical = index.lexical_search(query, allowed, limit=k * 3)
    fused = _fuse(dense, lexical)
    fused_score = dict(fused)
    guaranteed = [cid for cid, _ in dense[:GUARANTEED_PER_RETRIEVER]]
    guaranteed += [cid for cid, _ in lexical[:GUARANTEED_PER_RETRIEVER] if cid not in guaranteed]
    ordered = guaranteed + [cid for cid, _ in fused if cid not in guaranteed]
    out, per_doc_count = [], {}
    for cid in ordered:
        doc_id = index.chunks[cid].doc_id
        if doc_id not in allowed:  # defence in depth; the filters above already enforce this
            continue
        if per_doc_count.get(doc_id, 0) >= per_doc:
            continue
        per_doc_count[doc_id] = per_doc_count.get(doc_id, 0) + 1
        out.append((cid, fused_score.get(cid, 0.0)))
        if len(out) >= k:
            break
    return out


def search(
    index: CorpusIndex,
    query: str,
    requester: Requester,
    ref_date: date,
    *,
    k: int = 8,
    per_doc: int = 2,
    include_upcoming: bool = True,
    upcoming_k: int = 3,
) -> tuple[list[Hit], list[Hit]]:
    """Return (current hits, upcoming hits). Both only ever contain documents the requester may read."""
    allowed = eligible_doc_ids(index.docs, requester, ref_date)
    current = [
        Hit(index.chunks[cid], index.docs[index.chunks[cid].doc_id], s, False, ref_date.isoformat())
        for cid, s in _search(index, query, allowed, k, per_doc)
    ]
    upcoming: list[Hit] = []
    if include_upcoming:
        future_allowed = upcoming_doc_ids(index.docs, requester, ref_date)
        upcoming = [
            Hit(index.chunks[cid], index.docs[index.chunks[cid].doc_id], s, True, ref_date.isoformat())
            for cid, s in _search(index, query, future_allowed, upcoming_k, 1)
        ]
    return current, upcoming
