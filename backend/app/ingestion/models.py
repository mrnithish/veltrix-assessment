"""Shared ingestion types."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

VALID_DOC_TYPES = {"policy", "addendum", "memo", "handbook", "calendar", "faq", "wiki"}
VALID_ACCESS = {"all", "managers", "hr"}


@dataclass(frozen=True)
class DocMeta:
    doc_id: str
    file: str
    title: str
    doc_type: str
    regions: tuple[str, ...]
    effective_date: str  # YYYY-MM-DD
    access_level: str

    @property
    def is_global(self) -> bool:
        return "GLOBAL" in self.regions


@dataclass
class Block:
    """One structural element of a document, in reading order."""

    kind: str  # "heading" | "text" | "table"
    text: str = ""
    level: int = 0  # heading level: 1 = title, 2 = section, ...
    rows: list[list[str]] = field(default_factory=list)
    page: int | None = None


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    locator: str
    heading_path: list[str]
    text: str
    tokens: int
    page: int | None = None


def load_manifest(path: Path) -> list[DocMeta]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    docs: list[DocMeta] = []
    for item in raw:
        regions = item.get("regions") or ["GLOBAL"]
        docs.append(
            DocMeta(
                doc_id=str(item["doc_id"]),
                file=str(item["file"]),
                title=str(item.get("title") or item["doc_id"]),
                doc_type=str(item.get("doc_type", "policy")).lower(),
                regions=tuple(str(r).upper() for r in regions),
                effective_date=str(item["effective_date"]),
                access_level=str(item.get("access_level", "all")).lower(),
            )
        )
    return docs
