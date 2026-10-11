"""Готовая песня, которую человек вставил в идею, а не короткая просьба."""

from __future__ import annotations

import re

from backend.models import MusicAnalysis

_MIN_BODY_LINES = 8

_SECTION = re.compile(
    r"^(?:"
    r"(?P<final>final\s+chorus)|"
    r"(?P<pre>pre-?chorus|предприпев|пре-припев)|"
    r"(?P<verse>куплет|verse)|"
    r"(?P<chorus>припев|chorus)|"
    r"(?P<bridge>бридж|bridge)|"
    r"(?P<outro>аутро|outro)|"
    r"(?P<intro>интро|intro)"
    r")(?:\s+(?P<num>\d+))?\b",
    re.IGNORECASE,
)
_META = re.compile(r"^(?:жанр|настроение|текст песни)\b", re.IGNORECASE)
_ADVICE = re.compile(r"^совет\b", re.IGNORECASE)


def extract_provided_song(idea: str) -> str:
    """Вернуть текст песни или пустую строку, если это не готовая песня.

    Нужны и куплет, и припев, и не меньше восьми поющихся строк.
    Шапка чата и «совет для генерации» в песню не входят.
    """
    text = (idea or "").replace("\r\n", "\n").strip()
    if not text:
        return ""

    out: list[str] = []
    seen_verse = False
    seen_chorus = False
    verse_n = 0
    started = False

    for raw in text.splitlines():
        if _is_advice(raw):
            break
        kind = _section_kind(raw)
        if kind:
            started = True
            name, num = kind
            if name == "verse":
                seen_verse = True
                verse_n = num or verse_n + 1
                out.append(f"[Verse {verse_n}]")
            elif name == "chorus":
                seen_chorus = True
                out.append("[Chorus]")
            elif name == "final":
                seen_chorus = True
                out.append("[Final Chorus]")
            elif name == "pre":
                out.append("[Pre-Chorus]")
            elif name == "bridge":
                out.append("[Bridge]")
            elif name == "outro":
                out.append("[Outro]")
            elif name == "intro":
                out.append("[Intro]")
            continue
        if not started or _is_meta(raw):
            continue
        if not raw.strip():
            if out and out[-1] != "":
                out.append("")
            continue
        out.append(raw.strip())

    body = [line for line in out if line.strip() and not line.startswith("[")]
    if not seen_verse or not seen_chorus or len(body) < _MIN_BODY_LINES:
        return ""
    return "\n".join(out).strip()


def title_from_provided(lyrics: str) -> str:
    grab = False
    for line in (lyrics or "").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("[chorus"):
            grab = True
            continue
        if grab and stripped and not stripped.startswith("["):
            words = stripped.strip(" .,!?:;—-\"'«»").split()
            title = " ".join(words[:6]).strip(" .,!?:;—-")
            if title:
                return title
    return "Моя песня"


def style_from_analysis(analysis: MusicAnalysis) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for bit in (
        analysis.genre,
        analysis.subgenre,
        analysis.mood,
        analysis.vocal_description,
        analysis.production_style,
    ):
        text = (bit or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            parts.append(text)
    if analysis.instruments:
        parts.append(", ".join(str(item) for item in analysis.instruments[:5]))
    return ", ".join(parts)


def _label_text(line: str) -> str:
    raw = (line or "").strip()
    if not raw:
        return ""
    if raw.startswith("["):
        inner = raw[1:].split("]", 1)[0]
        return inner.split("—", 1)[0].split(" - ", 1)[0].strip()
    bare = raw.strip("*_ ").strip("()").strip("*_ ").strip()
    if len(bare) > 32:
        return ""
    return bare


def _section_kind(line: str) -> tuple[str, int] | None:
    match = _SECTION.match(_label_text(line))
    if not match:
        return None
    number = int(match.group("num")) if match.group("num") else 0
    for name in ("final", "pre", "verse", "chorus", "bridge", "outro", "intro"):
        if match.group(name):
            return name, number
    return None


def _bare_start(line: str) -> str:
    return (line or "").strip().strip("*_ ").strip().lower()


def _is_advice(line: str) -> bool:
    return bool(_ADVICE.match(_bare_start(line)))


def _is_meta(line: str) -> bool:
    return bool(_META.match(_bare_start(line)))
