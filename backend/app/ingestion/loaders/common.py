"""Helpers shared by the format loaders."""

from __future__ import annotations

import re

from app.ingestion.models import Block

_WS = re.compile(r"[ \t ]+")
NUMBERED_HEADING = re.compile(r"^(\d+(\.\d+)*)\.?\s+[A-Z][^.!?]{0,80}$")


def clean(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace("­", "")
    return "\n".join(_WS.sub(" ", line).strip() for line in text.splitlines()).strip()


def is_metadata_table(rows: list[list[str]]) -> bool:
    """The document-control table at the top of each file (Document ID, Version, ...).

    Its values duplicate manifest.json, so it is skipped to save context tokens.
    """
    for row in rows:
        for cell in row[:2]:
            first_line = (cell or "").strip().splitlines()[0].strip().lower() if (cell or "").strip() else ""
            if first_line == "document id":
                return True
    return False


def table_block(rows: list[list[str]], page: int | None = None) -> Block | None:
    cleaned = [[clean(c or "").replace("\n", " ") for c in row] for row in rows]
    cleaned = [r for r in cleaned if any(c for c in r)]
    if not cleaned or is_metadata_table(rows):
        return None
    return Block(kind="table", rows=cleaned, page=page)


def table_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(norm[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in norm[1:]]
    return "\n".join(lines)
