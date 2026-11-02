"""DOCX loader: paragraphs (heading styles) and tables in document order."""

from __future__ import annotations

import re
from pathlib import Path

import docx
from docx.table import Table

from app.ingestion.loaders.common import NUMBERED_HEADING, clean, table_block
from app.ingestion.models import Block

_HEADING_STYLE = re.compile(r"heading\s*(\d+)", re.IGNORECASE)


def _heading_level(paragraph) -> int | None:
    style = paragraph.style.name if paragraph.style is not None else ""
    if style.lower() == "title":
        return 1
    m = _HEADING_STYLE.search(style or "")
    if m:
        return int(m.group(1)) + 1
    text = paragraph.text.strip()
    runs = [r for r in paragraph.runs if r.text.strip()]
    if runs and all(r.bold for r in runs) and NUMBERED_HEADING.match(text):
        return 2
    return None


def load_docx(path: Path) -> list[Block]:
    document = docx.Document(str(path))
    blocks: list[Block] = []
    for item in document.iter_inner_content():
        if isinstance(item, Table):
            rows = []
            for row in item.rows:
                cells, seen = [], set()
                for cell in row.cells:  # merged cells repeat; keep each once
                    if id(cell._tc) in seen:
                        continue
                    seen.add(id(cell._tc))
                    cells.append(cell.text)
                rows.append(cells)
            tb = table_block(rows)
            if tb:
                blocks.append(tb)
            continue
        text = clean(item.text)
        if not text:
            continue
        level = _heading_level(item)
        if level:
            blocks.append(Block(kind="heading", text=text, level=level))
        else:
            style = (item.style.name if item.style is not None else "").lower()
            prefix = "- " if "list" in style else ""
            blocks.append(Block(kind="text", text=prefix + text))
    return blocks
