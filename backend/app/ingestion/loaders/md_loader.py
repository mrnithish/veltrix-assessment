"""Markdown loader: '#' headings, pipe tables, paragraphs and list items."""

from __future__ import annotations

import re
from pathlib import Path

from app.ingestion.loaders.common import clean, table_block
from app.ingestion.models import Block

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_SEPARATOR = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")


def _strip_inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.replace("`", "")


def load_markdown(path: Path) -> list[Block]:
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    blocks: list[Block] = []
    para: list[str] = []
    table: list[list[str]] = []

    def flush_para() -> None:
        if para:
            blocks.append(Block(kind="text", text=clean(_strip_inline(" ".join(para)))))
            para.clear()

    def flush_table() -> None:
        if table:
            tb = table_block(table)
            if tb:
                blocks.append(tb)
            table.clear()

    for raw in lines:
        line = raw.strip()
        if line.startswith("|"):
            flush_para()
            if not _SEPARATOR.match(line):
                table.append([_strip_inline(c) for c in line.strip("|").split("|")])
            continue
        flush_table()
        m = _HEADING.match(line)
        if m:
            flush_para()
            blocks.append(Block(kind="heading", text=clean(_strip_inline(m.group(2))), level=len(m.group(1))))
        elif not line:
            flush_para()
        elif re.match(r"^([-*+]|\d+[.)])\s+", line):
            flush_para()
            item = re.sub(r"^([-*+]|\d+[.)])\s+", "", line)
            blocks.append(Block(kind="text", text="- " + clean(_strip_inline(item))))
        else:
            para.append(line)
    flush_para()
    flush_table()
    return blocks
