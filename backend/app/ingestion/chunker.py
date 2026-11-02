"""Section-aware chunking.

One chunk = one section (text under the nearest heading), split further only when it is
larger than MAX_CHUNK_TOKENS. Tables stay whole where possible; when split, the header row
is repeated. Each chunk's locator is its nearest section heading, or "p. N" when the
document has no headings.
"""

from __future__ import annotations

import re

from app.ingestion.loaders.common import table_to_markdown
from app.ingestion.models import Block, Chunk, DocMeta
from app.llm.tokens import count_tokens

MAX_CHUNK_TOKENS = 380


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s).strip().lower()


def _split_table(rows: list[list[str]], max_tokens: int) -> list[str]:
    header, body = rows[0], rows[1:]
    parts, current = [], []
    for row in body:
        candidate = table_to_markdown([header, *current, row])
        if current and count_tokens(candidate) > max_tokens:
            parts.append(table_to_markdown([header, *current]))
            current = []
        current.append(row)
    parts.append(table_to_markdown([header, *current]))
    return parts


def _split_text(text: str, max_tokens: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    parts, current = [], ""
    for s in sentences:
        candidate = (current + " " + s).strip()
        if current and count_tokens(candidate) > max_tokens:
            parts.append(current)
            current = s
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def chunk_document(meta: DocMeta, blocks: list[Block], max_tokens: int = MAX_CHUNK_TOKENS) -> list[Chunk]:
    title_norm = _norm(meta.title)
    has_section_headings = any(b.kind == "heading" and _norm(b.text) != title_norm for b in blocks)
    chunks: list[Chunk] = []
    stack: list[tuple[int, str]] = []  # (level, heading) excluding the title
    units: list[tuple[str, int | None]] = []  # (text, page)

    def locator(page: int | None) -> str:
        if stack:
            return stack[-1][1]
        if page is not None and (not has_section_headings or meta.file.lower().endswith(".pdf")):
            return f"p. {page}"
        return meta.title

    def flush() -> None:
        if not units:
            return
        path = [h for _, h in stack]
        prefix = (" > ".join(path) + "\n") if path else ""
        budget = max_tokens - count_tokens(prefix)
        first_page = next((p for _, p in units if p is not None), None)
        pieces: list[str] = []
        current = ""
        for text, _page in units:
            candidate = (current + "\n" + text).strip() if current else text
            if count_tokens(candidate) <= budget:
                current = candidate
                continue
            if current:
                pieces.append(current)
            current = text if count_tokens(text) <= budget else ""
            if not current:  # a single oversized unit: split it
                splitter = _split_table if text.startswith("| ") else None
                if splitter:
                    rows = [
                        [c.strip() for c in ln.strip("|").split("|")]
                        for ln in text.splitlines()
                        if not ln.startswith("|---")
                    ]
                    pieces.extend(_split_table(rows, budget))
                else:
                    pieces.extend(_split_text(text, budget))
        if current:
            pieces.append(current)
        for piece in pieces:
            body = prefix + piece
            chunks.append(
                Chunk(
                    chunk_id=f"{meta.doc_id}#{len(chunks) + 1}",
                    doc_id=meta.doc_id,
                    locator=locator(first_page),
                    heading_path=path,
                    text=body,
                    tokens=count_tokens(body),
                    page=first_page,
                )
            )
        units.clear()

    for block in blocks:
        if block.kind == "heading":
            flush()
            if _norm(block.text) == title_norm:
                stack.clear()
                continue
            while stack and stack[-1][0] >= block.level:
                stack.pop()
            stack.append((block.level, block.text))
        elif block.kind == "table":
            units.append((table_to_markdown(block.rows), block.page))
        elif block.text:
            units.append((block.text, block.page))
    flush()
    return chunks
