"""Corpus index: Qdrant (dense vectors + payload filter) and BM25 (lexical), built at ingestion."""

from __future__ import annotations

import re
import time
import uuid

from qdrant_client import QdrantClient, models
from rank_bm25 import BM25Okapi

from app.ingestion.models import Chunk, DocMeta
from app.observability.logging import get_logger

log = get_logger(__name__)

COLLECTION = "veltrix_chunks"
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    ["a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "is", "are", "be", "by", "with", "at", "as", "do", "does", "i", "my", "me", "you", "your", "we", "our", "it", "this", "that", "how", "what", "when", "which", "who", "can", "will", "from"]
)


def tokenize(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


class CorpusIndex:
    def __init__(self, docs: dict[str, DocMeta], chunks: list[Chunk], embedder, qdrant_url: str = ""):
        self.docs = docs
        self.chunks = {c.chunk_id: c for c in chunks}
        self._order = [c.chunk_id for c in chunks]
        self.embedder = embedder
        self._remote = bool(qdrant_url)
        self.client = self._connect(qdrant_url)
        self._bm25 = BM25Okapi([tokenize(c.text + " " + docs[c.doc_id].title) for c in chunks]) if chunks else None
        self._build_vectors(chunks)

    @staticmethod
    def _connect(url: str) -> QdrantClient:
        if not url:
            return QdrantClient(":memory:")
        deadline = time.time() + 120
        while True:
            try:
                client = QdrantClient(url=url, timeout=30)
                client.get_collections()
                return client
            except Exception as exc:  # Qdrant container may still be starting
                if time.time() > deadline:
                    raise
                log.info("qdrant_waiting", error=str(exc)[:200])
                time.sleep(2)

    def _build_vectors(self, chunks: list[Chunk]) -> None:
        if self.client.collection_exists(COLLECTION):
            self.client.delete_collection(COLLECTION)
        self.client.create_collection(
            COLLECTION,
            vectors_config=models.VectorParams(size=self.embedder.dim, distance=models.Distance.COSINE),
        )
        if self._remote:
            self.client.create_payload_index(COLLECTION, "doc_id", models.PayloadSchemaType.KEYWORD)
        if not chunks:
            return
        # Embed title + heading path + text so short sections still carry their topic.
        texts = [f"{self.docs[c.doc_id].title}\n{c.text}" for c in chunks]
        vectors = self.embedder.embed_documents(texts)
        points = [
            models.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, c.chunk_id)),
                vector=v,
                payload={
                    "chunk_id": c.chunk_id,
                    "doc_id": c.doc_id,
                    "access_level": self.docs[c.doc_id].access_level,
                    "regions": list(self.docs[c.doc_id].regions),
                    "effective_date": self.docs[c.doc_id].effective_date,
                },
            )
            for c, v in zip(chunks, vectors)
        ]
        self.client.upsert(COLLECTION, points=points, wait=True)

    def dense_search(self, query: str, allowed_doc_ids: set[str], limit: int) -> list[tuple[str, float]]:
        """Vector search restricted (inside Qdrant) to the allowed documents."""
        if not allowed_doc_ids:
            return []
        flt = models.Filter(
            must=[models.FieldCondition(key="doc_id", match=models.MatchAny(any=sorted(allowed_doc_ids)))]
        )
        result = self.client.query_points(
            COLLECTION, query=self.embedder.embed_query(query), query_filter=flt, limit=limit, with_payload=True
        )
        return [(p.payload["chunk_id"], float(p.score)) for p in result.points]

    def lexical_search(self, query: str, allowed_doc_ids: set[str], limit: int) -> list[tuple[str, float]]:
        if not self._bm25 or not allowed_doc_ids:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        ranked = [
            (cid, float(s))
            for cid, s in zip(self._order, scores)
            if self.chunks[cid].doc_id in allowed_doc_ids and s > 0
        ]
        ranked.sort(key=lambda x: -x[1])
        return ranked[:limit]
