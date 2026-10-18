"""Нормализация полей запроса Suno V6 (лимиты sunoapi.org / ApiPass)."""

from __future__ import annotations

import re

from backend.utils.text import (
    clean_text,
    idea_allows_short_song,
    sung_lyrics_len,
    truncate,
)

# Suno V6: prompt до 5000; style в доке до 1000 — держим компактным (200).
SUNO_STYLE_MAX_LEN = 200
SUNO_TITLE_MAX_LEN = 80
SUNO_PROMPT_MAX_LEN = 5000
SUNO_NEGATIVE_MAX_LEN = 500
SUNO_DURATION_DEFAULT = 240
SUNO_DURATION_LONG = 300
SUNO_DURATION_MIN = 10
SUNO_DURATION_MAX = 360
# Поющиеся строки (без [Verse]/[Chorus]): обычная песня ~4 мин, дальше 5 и 6.
SUNO_BODY_LEN_FIVE_MIN = 2300
SUNO_BODY_LEN_SIX_MIN = 3200


def clamp_suno_duration(sec: int | None) -> int:
    try:
        value = int(sec or 0)
    except (TypeError, ValueError):
        value = 0
    if value <= 0:
        return SUNO_DURATION_DEFAULT
    return max(SUNO_DURATION_MIN, min(value, SUNO_DURATION_MAX))


def duration_from_lyrics(
    lyrics: str,
    *,
    requested_sec: int = 0,
    idea: str = "",
    instrumental: bool = False,
) -> int:
    """Длительность под готовый текст. Если человек указал минуты — его число.

    Потолок V6 — 360 сек (6 мин). 8 минут слать нельзя.
    Детские и инструментал не растягиваем.
    """
    try:
        requested = int(requested_sec or 0)
    except (TypeError, ValueError):
        requested = 0
    if requested > 0:
        return clamp_suno_duration(requested)
    if instrumental:
        return SUNO_DURATION_DEFAULT
    if idea_allows_short_song(idea):
        return SUNO_DURATION_DEFAULT

    body_len = sung_lyrics_len(lyrics)
    if body_len >= SUNO_BODY_LEN_SIX_MIN:
        return SUNO_DURATION_MAX
    if body_len >= SUNO_BODY_LEN_FIVE_MIN:
        return SUNO_DURATION_LONG
    return SUNO_DURATION_DEFAULT

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