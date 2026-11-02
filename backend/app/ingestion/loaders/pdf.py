"""PDF loader: text with font-based heading detection, tables, and OCR for scanned pages."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pymupdf

from app.ingestion.loaders.common import NUMBERED_HEADING, clean, table_block
from app.ingestion.loaders.ocr import ocr_page
from app.ingestion.models import Block

BOLD = 16
BULLETS = {"•", "", "●", "▪", "-", "*"}


def _inside(bbox, rects) -> bool:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return any(r[0] - 1 <= cx <= r[2] + 1 and r[1] - 1 <= cy <= r[3] + 1 for r in rects)


def _find_tables(page) -> list:
    """Line-based table detection. The optional ONNX layout model is disabled: it is not
    deterministic across machines and can fail under memory pressure."""
    try:
        found = page.find_tables(use_layout=False)
    except TypeError:  # older PyMuPDF without the use_layout switch
        found = page.find_tables()
    except Exception:
        return []
    return list(found.tables) if found is not None else []


def _extract_table(page, table) -> list[list[str]]:
    """Read each cell by its bounding box (keeps word spacing, which Table.extract() can lose)."""
    rows: list[list[str]] = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            if cell is None:
                cells.append("")
                continue
            text = page.get_text("text", clip=pymupdf.Rect(cell)).strip()
            cells.append(text)
        rows.append(cells)
    return rows


def _ocr_blocks(page, page_no: int) -> list[Block]:
    text = clean(ocr_page(page))
    blocks: list[Block] = []
    for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
        lines = [ln for ln in para.splitlines() if ln.strip()]
        if len(lines) == 1 and NUMBERED_HEADING.match(lines[0]):
            blocks.append(Block(kind="heading", text=lines[0], level=2, page=page_no))
        else:
            blocks.append(Block(kind="text", text=" ".join(lines), page=page_no))
    return blocks


def load_pdf(path: Path) -> list[Block]:
    doc = pymupdf.open(str(path))
    pages = []
    size_counter: Counter[float] = Counter()
    for page in doc:
        data = page.get_text("dict")
        pages.append((page, data))
        for b in data["blocks"]:
            for line in b.get("lines", []):
                for s in line["spans"]:
                    size_counter[round(s["size"], 1)] += len(s["text"].strip())
    body_size = size_counter.most_common(1)[0][0] if size_counter else 10.0

    # First pass: collect candidate heading sizes so levels are consistent across pages.
    raw: list[tuple[int, float, str, str, Block | None]] = []  # (page, y, kind, text, table)
    heading_sizes: set[float] = set()
    for page_no, (page, data) in enumerate(pages, start=1):
        if len(page.get_text().strip()) < 20 and page.get_images():
            for blk in _ocr_blocks(page, page_no):
                raw.append((page_no, 0.0, "ocr", "", blk))
            continue
        height = page.rect.height
        tables = _find_tables(page)
        rects = [t.bbox for t in tables]
        for t in tables:
            tb = table_block(_extract_table(page, t), page_no)
            if tb:
                raw.append((page_no, t.bbox[1], "table", "", tb))
        for b in data["blocks"]:
            if b.get("type") != 0 or _inside(b["bbox"], rects):
                continue
            for line in b.get("lines", []):
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = clean("".join(s["text"] for s in line["spans"]))
                size = max(round(s["size"], 1) for s in spans)
                y0, y1 = line["bbox"][1], line["bbox"][3]
                # Running header/footer: small text in the top/bottom margin.
                if size < body_size and (y0 > height * 0.92 or y1 < height * 0.06):
                    continue
                bold = all(s["flags"] & BOLD for s in spans)
                if bold and size > body_size * 1.15:
                    heading_sizes.add(size)
                    raw.append((page_no, y0, f"h:{size}", text, None))
                else:
                    raw.append((page_no, y0, "line", text, None))

    levels = {s: i + 1 for i, s in enumerate(sorted(heading_sizes, reverse=True))}
    raw.sort(key=lambda r: (r[0], r[1]))

    blocks: list[Block] = []
    para: list[str] = []
    para_page = None

    def flush() -> None:
        nonlocal para, para_page
        if para:
            blocks.append(Block(kind="text", text=" ".join(para).strip(), page=para_page))
        para, para_page = [], None

    for page_no, _y, kind, text, blk in raw:
        if kind in ("table", "ocr"):
            flush()
            blocks.append(blk)
        elif kind.startswith("h:"):
            flush()
            blocks.append(Block(kind="heading", text=text, level=levels[float(kind[2:])], page=page_no))
        else:
            if text in BULLETS:  # bullet glyph on its own line starts a new list item
                flush()
                para, para_page = ["-"], page_no
                continue
            if para and para != ["-"] and text[:1] in BULLETS:
                flush()
            if not para:
                para_page = page_no
            para.append(text)
    flush()
    return blocks
