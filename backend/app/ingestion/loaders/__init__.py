"""Format dispatch for corpus files."""

from __future__ import annotations

from pathlib import Path

from app.ingestion.models import Block


def load_blocks(path: Path) -> list[Block]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from app.ingestion.loaders.pdf import load_pdf

        return load_pdf(path)
    if suffix == ".docx":
        from app.ingestion.loaders.docx_loader import load_docx

        return load_docx(path)
    if suffix in (".html", ".htm"):
        from app.ingestion.loaders.html_loader import load_html

        return load_html(path)
    if suffix in (".md", ".markdown", ".txt"):
        from app.ingestion.loaders.md_loader import load_markdown

        return load_markdown(path)
    raise ValueError(f"Unsupported file type: {path.name}")
