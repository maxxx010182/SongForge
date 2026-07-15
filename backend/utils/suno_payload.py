"""Нормализация полей запроса Suno V5.5 (лимиты ApiPass / sunoapi.org)."""

from __future__ import annotations

import re

from backend.utils.text import clean_text, truncate

# Suno V5.5 / ApiPass: prompt до 5000; style держим компактным (200) для стабильности
# (docs V5.5 style до 1000 — не раздуваем, качество важнее длины style).
SUNO_STYLE_MAX_LEN = 200
SUNO_TITLE_MAX_LEN = 80
SUNO_PROMPT_MAX_LEN = 5000
SUNO_NEGATIVE_MAX_LEN = 500

_TITLE_BAD_RE = re.compile(
    r"^\[|crowd noise|stadium ambience|intro\s*[-—]|outro\s*[-—]|verse\s*\d",
    re.IGNORECASE,
)

_TITLE_SKIP_WORDS = frozenset(
    {
        "гимн",
        "песня",
        "песню",
        "трек",
        "про",
        "о",
        "на",
        "моя",
        "мой",
        "моё",
        "это",
        "мой",
        "наш",
        "наша",
    }
)


def compact_suno_style(style: str, max_len: int = SUNO_STYLE_MAX_LEN) -> str:
    """Убрать дубли и уложить style в лимит Suno."""
    text = clean_text(style).strip()
    if not text:
        return "modern commercial production, sung in Russian, native Russian vocals"
    if len(text) <= max_len:
        return text

    parts = [p.strip() for p in text.split(",") if p.strip()]
    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(part)

    chosen: list[str] = []
    length = 0
    for part in unique:
        extra = len(part) + (2 if chosen else 0)
        if length + extra > max_len:
            break
        chosen.append(part)
        length += extra

    if chosen:
        return ", ".join(chosen)
    return truncate(text, max_len)


def sanitize_suno_title(title: str, idea: str = "") -> str:
    """Название — короткое имя песни, не сценическая ремарка из текста."""
    cleaned = clean_text(title).strip().strip("\"'«»")
    if cleaned and not _TITLE_BAD_RE.search(cleaned) and len(cleaned) <= 60:
        return truncate(cleaned, SUNO_TITLE_MAX_LEN)

    idea_text = (idea or "").strip()
    cyrillic = [
        w
        for w in re.findall(r"[А-Яа-яЁё]{3,}", idea_text)
        if w.lower() not in _TITLE_SKIP_WORDS
    ]
    if cyrillic:
        best = max(cyrillic, key=len)
        return truncate(best.capitalize(), SUNO_TITLE_MAX_LEN)

    latin = re.findall(r"[A-Za-z]{3,}", idea_text)
    if latin:
        return truncate(latin[0].capitalize(), SUNO_TITLE_MAX_LEN)

    return "Моя песня"


def sanitize_negative_tags(negative_tags: str, style: str, genre: str = "") -> str:
    """Не запрещать distortion/crowd/screaming для rock/stadium/rap-rock."""
    text = clean_text(negative_tags).strip()
    if not text:
        return text

    context = f"{style} {genre}".lower()
    stadium_like = any(
        token in context
        for token in (
            "stadium",
            "arena",
            "anthem",
            "rap-rock",
            "rap rock",
            "distorted guitar",
            "crowd",
            "live concert",
            "rock",
        )
    )
    if not stadium_like:
        return truncate(text, SUNO_NEGATIVE_MAX_LEN)

    drop = {
        "distortion",
        "screaming",
        "unwanted noise",
    }
    parts = [p.strip() for p in text.split(",") if p.strip()]
    filtered = [p for p in parts if p.lower() not in drop]
    return truncate(", ".join(filtered) if filtered else text, SUNO_NEGATIVE_MAX_LEN)


def clamp_suno_prompt(prompt: str) -> str:
    return truncate(clean_text(prompt), SUNO_PROMPT_MAX_LEN)