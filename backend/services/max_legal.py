"""Юрдокументы в чат MAX: простой текст, без ухода на сайт."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from backend.legal_pages import LEGAL_HTML_DIR, _PAGES

MAX_CHUNK = 3500


class _HtmlText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style"}:
            self._skip = True
        if tag in {"p", "h2", "h3", "li", "br", "div"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._skip = False
        if tag in {"p", "h2", "h3", "li"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = data.replace("\xa0", " ").strip()
        if text:
            self._parts.append(text)

    def text(self) -> str:
        raw = " ".join(self._parts)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n[ \t]+", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def html_to_text(html: str) -> str:
    parser = _HtmlText()
    parser.feed(html or "")
    parser.close()
    return parser.text()


def legal_chunks(slug: str) -> tuple[str, list[str]]:
    meta = _PAGES.get(slug)
    if not meta:
        return "", []
    path = LEGAL_HTML_DIR / meta["file"]
    if not path.is_file():
        return meta["title"], []
    body = html_to_text(path.read_text(encoding="utf-8"))
    title = str(meta["title"])
    updated = str(meta.get("updated") or "")
    head = title
    if updated:
        head += f"\nОбновлено: {updated}"
    full = f"{head}\n\n{body}".strip()
    return title, _split_chunks(full)


def _split_chunks(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK:
        return [text] if text else []
    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= MAX_CHUNK:
            chunks.append(rest.strip())
            break
        piece = rest[:MAX_CHUNK]
        cut = piece.rfind("\n\n")
        if cut < MAX_CHUNK // 2:
            cut = piece.rfind("\n")
        if cut < MAX_CHUNK // 2:
            cut = piece.rfind(". ")
            if cut != -1:
                cut += 1
        if cut < MAX_CHUNK // 2:
            cut = MAX_CHUNK
        chunks.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    return [c for c in chunks if c]


def legal_page(slug: str, page: int) -> tuple[str, int, int]:
    """Текст страницы page (1-based), номер, всего страниц."""
    _title, chunks = legal_chunks(slug)
    if not chunks:
        return "Документ сейчас недоступен. Напишите support@sozdaipesnu.ru", 1, 1
    total = len(chunks)
    idx = min(max(page, 1), total)
    text = chunks[idx - 1]
    if total > 1:
        text = f"{text}\n\n({idx}/{total})"
    return text, idx, total
