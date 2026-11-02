"""HTML loader: h1-h4 headings, paragraphs, list items and tables."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup, Tag

from app.ingestion.loaders.common import clean, table_block
from app.ingestion.models import Block

_SKIP = {"script", "style", "nav", "footer", "header", "noscript", "template", "head"}
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
_TEXT = {"p", "li", "dd", "dt", "blockquote", "pre", "figcaption"}


def load_html(path: Path) -> list[Block]:
    soup = BeautifulSoup(Path(path).read_text(encoding="utf-8", errors="replace"), "html.parser")
    for tag in soup.find_all(_SKIP):
        tag.decompose()
    root = soup.body or soup
    blocks: list[Block] = []

    def walk(node: Tag) -> None:
        for child in node.children:
            if not isinstance(child, Tag):
                text = clean(str(child))
                if text and node is root:
                    blocks.append(Block(kind="text", text=text))
                continue
            name = child.name.lower()
            if name in _HEADINGS:
                text = clean(child.get_text(" "))
                if text:
                    blocks.append(Block(kind="heading", text=text, level=_HEADINGS[name]))
            elif name == "table":
                rows = [
                    [cell.get_text(" ") for cell in tr.find_all(["td", "th"])] for tr in child.find_all("tr")
                ]
                tb = table_block(rows)
                if tb:
                    blocks.append(tb)
            elif name in _TEXT:
                text = clean(child.get_text(" "))
                if text:
                    blocks.append(Block(kind="text", text=("- " + text) if name == "li" else text))
            else:
                walk(child)

    walk(root)
    return blocks
