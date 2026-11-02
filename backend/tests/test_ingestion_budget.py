import asyncio
from dataclasses import replace
from datetime import date

import pytest

from app.config import CORPUS_TOKEN_BUDGET
from app.ingestion.chunker import MAX_CHUNK_TOKENS
from app.ingestion.loaders.ocr import boxes_to_text, ocr_available
from app.llm.base import call_llm
from app.llm.fake import FakeLLM
from app.retrieval.budget import BudgetExceeded, pack
from app.retrieval.eligibility import Requester
from app.retrieval.search import search


def test_every_format_is_ingested(corpus):
    docs_with_chunks = {c.doc_id for c in corpus.chunks}
    for doc_id in ("POL-VOL-V1", "POL-VOL-V2", "CAL-IN-2026", "POL-TRAVEL"):  # md, docx, html, pdf
        assert doc_id in docs_with_chunks


def test_metadata_table_skipped_and_locators_are_headings(corpus):
    v2 = [c for c in corpus.chunks if c.doc_id == "POL-VOL-V2"]
    assert all("Document ID" not in c.text for c in v2)
    assert {c.locator for c in v2} == {"1. Volunteer days", "2. Sick leave"}
    pdf = [c for c in corpus.chunks if c.doc_id == "POL-TRAVEL"]
    assert {c.locator for c in pdf} == {"1. Hotels", "2. Meals"}


def test_tables_are_kept_as_rows(corpus):
    sick = next(c for c in corpus.chunks if c.doc_id == "POL-VOL-V2" and c.locator == "2. Sick leave")
    assert "| Sick days per year | 12 working days |" in sick.text


def test_chunks_respect_size_limit(corpus):
    assert max(c.tokens for c in corpus.chunks) <= MAX_CHUNK_TOKENS


def test_holidays_extracted_with_restricted_kind(corpus):
    kinds = {(h.date.isoformat(), h.kind) for h in corpus.holidays["CAL-IN-2026"]}
    assert ("2026-06-19", "public") in kinds and ("2026-06-17", "restricted") in kinds


@pytest.mark.skipif(not ocr_available(), reason="rapidocr not installed")
def test_scanned_pdf_is_ocrd(corpus):
    text = " ".join(c.text for c in corpus.chunks if c.doc_id == "MEMO-SCAN").lower()
    assert "work from home" in text and "3 days" in text
    assert all(c.locator == "p. 1" for c in corpus.chunks if c.doc_id == "MEMO-SCAN")


def test_pack_never_exceeds_budget(corpus):
    req = Requester("E100", "hr", "IN")
    hits, upcoming = search(corpus.index, "volunteer sick holiday travel", req, date(2026, 6, 15), k=50, per_doc=10)
    big = [  # far more distinct text than the budget allows
        replace(h, chunk=replace(h.chunk, chunk_id=f"{h.chunk.chunk_id}-{i}"))
        for i, h in enumerate(hits * 40)
    ]
    p = pack(big, upcoming)
    assert p.tokens <= CORPUS_TOKEN_BUDGET
    assert p.dropped


def test_llm_call_refuses_over_budget():
    with pytest.raises(BudgetExceeded):
        asyncio.run(call_llm(FakeLLM(), [{"role": "user", "content": "x"}], purpose="t",
                             corpus_tokens=CORPUS_TOKEN_BUDGET + 1))


def test_ocr_boxes_become_lines_and_paragraphs():
    def box(x, y, w=200, h=20):
        return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]

    boxes = [box(10, 10), box(220, 12), box(10, 40), box(10, 120), box(10, 300, h=40)]
    texts = ["Hybrid work", "update", "up to 3 days per week.", "Core hours unchanged.", "scribble"]
    scores = [0.99, 0.98, 0.97, 0.99, 0.5]  # the last box is a low-confidence signature
    expected = "Hybrid work update\nup to 3 days per week.\n\nCore hours unchanged."
    assert boxes_to_text(boxes, texts, scores) == expected
