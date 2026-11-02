"""OCR for scanned PDF pages (pages with no text layer), using RapidOCR (PP-OCR models on ONNX Runtime, CPU).

RapidOCR returns text boxes. They are rebuilt into lines (boxes whose vertical centres overlap) and
paragraphs (a vertical gap clearly larger than normal line spacing), so the chunker sees the same
paragraph structure as a text PDF. Low-confidence boxes (e.g. a handwritten signature) are dropped.
"""

from __future__ import annotations

import itertools
import os
import statistics
import threading

from app.observability.logging import get_logger

log = get_logger(__name__)

MIN_SCORE = float(os.environ.get("OCR_MIN_SCORE", "0.8"))
OCR_DPI = int(os.environ.get("OCR_DPI", "200"))

_engine = None
_lock = threading.Lock()


def _get_engine():
    global _engine
    with _lock:
        if _engine is None:
            from rapidocr import RapidOCR

            _engine = RapidOCR()
        return _engine


def ocr_available() -> bool:
    try:
        import rapidocr  # noqa: F401
    except ImportError:
        return False
    return True


def boxes_to_text(boxes, texts, scores, min_score: float = MIN_SCORE) -> str:
    """Rebuild reading order: lines top-to-bottom, words left-to-right, blank line between paragraphs."""
    items = []
    for box, text, score in zip(boxes, texts, scores):
        if float(score) < min_score or not str(text).strip():
            continue
        ys = [float(p[1]) for p in box]
        xs = [float(p[0]) for p in box]
        items.append({"top": min(ys), "bottom": max(ys), "left": min(xs), "text": str(text).strip()})
    if not items:
        return ""
    items.sort(key=lambda i: (i["top"], i["left"]))

    lines: list[list[dict]] = []
    for it in items:
        centre = (it["top"] + it["bottom"]) / 2
        if lines:
            last = lines[-1]
            top, bottom = min(i["top"] for i in last), max(i["bottom"] for i in last)
            if top <= centre <= bottom:
                last.append(it)
                continue
        lines.append([it])

    rows = [{"top": min(i["top"] for i in ln), "bottom": max(i["bottom"] for i in ln),
             "text": " ".join(i["text"] for i in sorted(ln, key=lambda i: i["left"]))} for ln in lines]
    gaps = [b["top"] - a["bottom"] for a, b in itertools.pairwise(rows)]
    typical = statistics.median(gaps) if gaps else 0.0
    out = [rows[0]["text"]]
    for gap, row in zip(gaps, rows[1:]):
        out.append(("\n\n" if typical and gap > typical * 1.6 else "\n") + row["text"])
    return "".join(out)


def ocr_page(page, dpi: int = OCR_DPI) -> str:
    """Render one PyMuPDF page and return its OCR text. Empty string if OCR is unavailable."""
    if not ocr_available():
        log.warning("ocr_unavailable", reason="rapidocr not installed")
        return ""
    png = page.get_pixmap(dpi=dpi).tobytes("png")
    result = _get_engine()(png)
    if result is None or result.txts is None:
        return ""
    text = boxes_to_text(result.boxes, result.txts, result.scores)
    log.info("ocr_page", engine="rapidocr", boxes=len(result.txts), chars=len(text))
    return text
