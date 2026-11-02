"""Automatic ingestion: manifest + corpus -> chunks, holiday records and the search index."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from app.config import Settings
from app.data import state
from app.ingestion.chunker import chunk_document
from app.ingestion.holidays import extract_holidays
from app.ingestion.loaders import load_blocks
from app.ingestion.models import Chunk, DocMeta, load_manifest
from app.observability.logging import get_logger
from app.observability.tracing import tracer
from app.retrieval.embeddings import make_embedder
from app.retrieval.index import CorpusIndex

log = get_logger(__name__)


@dataclass
class Holiday:
    date: date
    name: str
    kind: str  # "public" | "restricted"


@dataclass
class Corpus:
    docs: dict[str, DocMeta]
    chunks: list[Chunk]
    index: CorpusIndex
    holidays: dict[str, list[Holiday]] = field(default_factory=dict)  # doc_id -> holidays
    stats: dict = field(default_factory=dict)


def run_ingestion(settings: Settings) -> Corpus:
    started = time.time()
    with tracer().start_as_current_span("ingestion.run") as span:
        docs_list = load_manifest(settings.manifest_path)
        docs = {d.doc_id: d for d in docs_list}
        chunks: list[Chunk] = []
        holiday_rows: list[dict] = []
        per_doc: dict[str, dict] = {}
        for meta in docs_list:
            path = settings.corpus_dir / meta.file
            with tracer().start_as_current_span("ingestion.document") as doc_span:
                doc_span.set_attribute("doc_id", meta.doc_id)
                doc_span.set_attribute("format", path.suffix.lower())
                if not path.exists():
                    log.error("ingestion_missing_file", doc_id=meta.doc_id, file=meta.file)
                    per_doc[meta.doc_id] = {"error": "missing file"}
                    continue
                try:
                    blocks = load_blocks(path)
                except Exception as exc:  # one bad file must not stop ingestion
                    log.exception("ingestion_failed", doc_id=meta.doc_id, error=str(exc))
                    per_doc[meta.doc_id] = {"error": str(exc)[:200]}
                    continue
                doc_chunks = chunk_document(meta, blocks)
                hol = extract_holidays(meta, blocks)
                chunks.extend(doc_chunks)
                holiday_rows.extend(hol)
                per_doc[meta.doc_id] = {
                    "blocks": len(blocks),
                    "chunks": len(doc_chunks),
                    "tables": sum(1 for b in blocks if b.kind == "table"),
                    "holidays": len(hol),
                }
                doc_span.set_attribute("chunks", len(doc_chunks))
                if not doc_chunks:
                    log.warning("ingestion_empty_document", doc_id=meta.doc_id)

        state.replace_holidays(holiday_rows)
        holidays: dict[str, list[Holiday]] = defaultdict(list)
        for row in holiday_rows:
            holidays[row["doc_id"]].append(Holiday(date.fromisoformat(row["date"]), row["name"], row["kind"]))

        embedder = make_embedder(settings.embedding_backend, settings.embedding_model)
        index = CorpusIndex(docs, chunks, embedder, settings.qdrant_url)
        stats = {
            "documents": len(docs),
            "chunks": len(chunks),
            "holiday_records": len(holiday_rows),
            "seconds": round(time.time() - started, 2),
            "per_doc": per_doc,
        }
        span.set_attribute("documents", len(docs))
        span.set_attribute("chunks", len(chunks))
        log.info("ingestion_complete", documents=len(docs), chunks=len(chunks),
                 holiday_records=len(holiday_rows), seconds=stats["seconds"])
        return Corpus(docs=docs, chunks=chunks, index=index, holidays=dict(holidays), stats=stats)


_corpus: Corpus | None = None


def set_corpus(corpus: Corpus | None) -> None:
    global _corpus
    _corpus = corpus


def get_corpus() -> Corpus:
    if _corpus is None:
        raise RuntimeError("Corpus not ingested yet")
    return _corpus


def corpus_ready() -> bool:
    return _corpus is not None
