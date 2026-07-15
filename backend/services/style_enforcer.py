"""Дополняет style от AI: жанр из plan всегда главный (универсально, не только rap)."""

from __future__ import annotations

import re

from backend.models import ProductionPlan
from backend.services.idea_parser import is_rap_genre
from backend.services.reference_translator import ReferenceTranslation
from backend.utils.text import clean_text, ensure_russian_vocal_style

_MIN_STYLE_LEN = 80

# Сигнатуры жанров: head (в начало style) + чужие теги, которые вычищаем при конфликте.
# Универсально: Jazz не должен уезжать в Modern Pop, Rock — в hip-hop и т.д.
_GENRE_PROFILES: dict[str, dict[str, object]] = {
    "hip-hop": {
        "aliases": ("hip-hop", "hip hop", "rap", "trap", "drill"),
        "head": "Russian hip-hop, rap vocals, 808 drums, boom bap flow, urban beat",
        "strip": (
            r"modern\s+pop|upbeat\s+pop|cheerful\s+pop|bright\s+pop|dance\s+pop|"
            r"euro\s+pop|bubblegum\s+pop|synth[\s-]?pop|soft\s+pop|"
            r"orchestral\s+classical|country\s+twang|smooth\s+jazz"
        ),
    },
    "trap": {
        "aliases": ("trap",),
        "head": "dark trap, 808 bass, hi-hat rolls, rap vocals, urban beat",
        "strip": r"modern\s+pop|bubblegum|acoustic\s+ballad|orchestral\s+classical",
    },
    "drill": {
        "aliases": ("drill",),
        "head": "drill, sliding 808s, sparse dark beat, rap vocals",
        "strip": r"modern\s+pop|bubblegum|cheerful\s+pop|soft\s+ballad",
    },
    "rock": {
        "aliases": ("rock", "punk"),
        "head": "rock band, electric guitars, live drums, bass, energetic rock vocals",
        "strip": (
            r"modern\s+pop|bubblegum\s+pop|synth[\s-]?pop|hip[\s-]?hop|808\s+drums|"
            r"rap\s+vocals|trap\s+beat|lo[\s-]?fi\s+chill"
        ),
    },
    "metal": {
        "aliases": ("metal",),
        "head": "heavy metal, distorted guitars, double kick drums, powerful metal vocals",
        "strip": r"modern\s+pop|bubblegum|soft\s+acoustic|lo[\s-]?fi|smooth\s+jazz",
    },
    "pop": {
        "aliases": ("pop",),
        "head": "modern pop, catchy hooks, polished production, radio-ready",
        "strip": (
            r"heavy\s+metal|screaming\s+vocals|death\s+metal|raw\s+black\s+metal|"
            r"aggressive\s+drill"
        ),
    },
    "ballad": {
        "aliases": ("ballad",),
        "head": "emotional ballad, intimate vocals, soft piano, strings",
        "strip": (
            r"heavy\s+metal|aggressive\s+rap|hard\s+trap|screaming|"
            r"distorted\s+guitars,\s*double\s+kick"
        ),
    },
    "electronic": {
        "aliases": ("electronic", "edm", "techno", "house", "drum and bass", "dnb"),
        "head": "electronic production, synths, programmed drums, club energy",
        "strip": r"acoustic\s+guitar\s+ballad|country\s+twang|orchestral\s+classical\s+only",
    },
    "lo-fi": {
        "aliases": ("lo-fi", "lofi", "lo fi"),
        "head": "lo-fi hip-hop, dusty drums, chill vinyl texture, relaxed mood",
        "strip": r"heavy\s+metal|screaming|stadium\s+rock|aggressive\s+distortion",
    },
    "r&b": {
        "aliases": ("r&b", "r and b", "rnb", "soul"),
        "head": "modern R&B, smooth vocals, groove bass, warm keys",
        "strip": r"heavy\s+metal|screaming|aggressive\s+drill|punk\s+rock",
    },
    "jazz": {
        "aliases": ("jazz",),
        "head": "contemporary jazz, upright or electric bass, ride cymbals, improvisational feel",
        "strip": (
            r"modern\s+pop|bubblegum|heavy\s+metal|808\s+trap|screaming|"
            r"edm\s+drop"
        ),
    },
    "classical": {
        "aliases": ("classical", "orchestral"),
        "head": "orchestral, cinematic strings, classical instrumentation",
        "strip": r"808|trap\s+beat|heavy\s+metal\s+distortion|edm\s+drop|rap\s+vocals",
    },
    "country": {
        "aliases": ("country",),
        "head": "modern country, acoustic guitar, storytelling vocals, warm twang",
        "strip": r"heavy\s+metal|808\s+trap|edm\s+drop|drill",
    },
    "chanson": {
        "aliases": ("chanson", "шансон"),
        "head": "russian chanson, storytelling male vocal, acoustic guitar, nostalgic",
        "strip": r"edm\s+drop|heavy\s+metal|trap\s+808|bubblegum\s+pop",
    },
    "folk": {
        "aliases": ("folk",),
        "head": "folk, acoustic instruments, storytelling vocals, organic production",
        "strip": r"heavy\s+metal|trap\s+808|edm\s+drop",
    },
    "blues": {
        "aliases": ("blues",),
        "head": "blues, expressive vocals, guitar bends, swing feel",
        "strip": r"edm\s+drop|trap\s+808|bubblegum\s+pop",
    },
    "reggae": {
        "aliases": ("reggae",),
        "head": "reggae, offbeat guitar, deep bass, relaxed groove",
        "strip": r"heavy\s+metal|trap\s+drill|edm\s+festival\s+drop",
    },
}


def _contains(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()


def _append_unique(style: str, fragment: str) -> str:
    fragment = fragment.strip()
    if not fragment or _contains(style, fragment):
        return style
    if style.strip():
        return f"{style}, {fragment}"
    return fragment


def _genre_key(plan: ProductionPlan) -> str:
    blob = f"{plan.genre} {plan.subgenre}".lower()
    # Более специфичные первыми
    for key in (
        "drill",
        "trap",
        "hip-hop",
        "metal",
        "lo-fi",
        "r&b",
        "drum and bass",
        "electronic",
        "classical",
        "country",
        "chanson",
        "ballad",
        "jazz",
        "folk",
        "blues",
        "reggae",
        "rock",
        "pop",
    ):
        profile = _GENRE_PROFILES.get(key)
        if not profile:
            if key == "drum and bass" and ("drum" in blob and "bass" in blob):
                return "electronic"
            continue
        aliases = profile["aliases"]  # type: ignore[assignment]
        if any(a in blob for a in aliases):  # type: ignore[union-attr]
            return key
        if key.replace("-", " ") in blob or key in blob:
            return key
    # fallback: first word of genre
    first = (plan.genre or "pop").lower().split()[0]
    if first in _GENRE_PROFILES:
        return first
    return "pop"


def _strip_conflicting_tags(style: str, strip_pattern: str) -> str:
    if not strip_pattern:
        return style
    cleaned = re.sub(
        rf",?\s*\b(?:{strip_pattern})\b\s*,?",
        ", ",
        style,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s*,\s*,+", ", ", cleaned)
    return cleaned.strip(" ,")


def _plan_style_fallback(plan: ProductionPlan) -> str:
    parts = [
        f"Modern commercial {plan.genre}",
        plan.subgenre,
        f"{plan.mood} mood",
        f"{plan.bpm} BPM",
        f"{plan.energy} energy",
        ", ".join(plan.instruments) if plan.instruments else "",
        plan.vocal_description,
        plan.production_style,
        plan.atmosphere,
        "wide stereo",
        "radio-ready production",
        "crystal clear mix",
    ]
    return ", ".join(p for p in parts if p and p.strip())


def _prepend_genre_head(base: str, plan: ProductionPlan) -> str:
    """Жанр plan — в начало style (Suno сильнее смотрит на первые теги)."""
    key = _genre_key(plan)
    profile = _GENRE_PROFILES.get(key, {})
    head = str(profile.get("head") or f"{plan.genre} {plan.subgenre}".strip())
    strip = str(profile.get("strip") or "")

    if strip:
        base = _strip_conflicting_tags(base, strip)

    # Уже есть head-фрагменты — не дублируем целиком
    head_tokens = [t.strip() for t in head.split(",") if t.strip()]
    missing = [t for t in head_tokens if not _contains(base, t)]
    if missing:
        prefix = ", ".join(missing)
        base = f"{prefix}, {base}" if base else prefix

    # Явная строка genre/subgenre
    genre_line = f"{plan.genre} {plan.subgenre}".strip()
    if genre_line and not _contains(base, plan.genre):
        base = f"{genre_line}, {base}" if base else genre_line

    return base


def enforce_style(
    style: str,
    plan: ProductionPlan,
    *,
    reference: ReferenceTranslation | None = None,
    backing_vocal: bool = False,
    backing_vocal_gender: str = "",
) -> str:
    """База — AI style; жанр/вокал/референс выравниваем универсально."""
    base = clean_text(style).strip()

    if reference and reference.has_content and reference.style_tags:
        if not _contains(base, reference.style_tags):
            base = (
                f"{reference.style_tags}, {base}"
                if base
                else reference.style_tags
            )

    if len(base) < _MIN_STYLE_LEN:
        fallback = _plan_style_fallback(plan)
        base = f"{fallback}, {base}" if base else fallback

    base = _prepend_genre_head(base, plan)

    if plan.mood:
        base = _append_unique(base, f"{plan.mood} mood")
    if plan.bpm:
        base = _append_unique(base, f"{plan.bpm} BPM")
    if plan.energy:
        base = _append_unique(base, f"{plan.energy} energy")

    instruments = ", ".join(plan.instruments) if plan.instruments else ""
    if instruments:
        base = _append_unique(base, instruments)
    if plan.production_style:
        base = _append_unique(base, plan.production_style)
    if plan.atmosphere:
        base = _append_unique(base, plan.atmosphere)

    atmosphere = (plan.atmosphere or "").lower()
    ideaish = f"{plan.atmosphere} {plan.production_style}".lower()
    if plan.energy == "high" or any(
        t in atmosphere or t in ideaish
        for t in ("stadium", "live", "concert", "crowd", "arena", "стадион")
    ):
        base = _append_unique(
            base, "live energy, concert atmosphere, wide stereo"
        )

    # Вокал — без принудительного «rap delivery» вне hip-hop
    rap = is_rap_genre(plan.genre, plan.subgenre)
    if plan.vocal == "duet":
        if rap:
            base = _append_unique(
                base,
                "male and female duet vocals, dual lead vocals, "
                "male rap verses with female sung hook",
            )
        else:
            base = _append_unique(
                base,
                "male and female duet vocals, dual lead vocals, "
                "alternating male and female verses",
            )
    elif plan.vocal == "male":
        if rap:
            base = _append_unique(base, "male lead vocals, deep male rap delivery")
        else:
            base = _append_unique(base, "male lead vocals")
    elif plan.vocal == "female":
        base = _append_unique(base, "female lead vocals")

    if backing_vocal:
        if backing_vocal_gender == "f":
            base = _append_unique(
                base,
                "female backing vocals, layered female harmonies, "
                "female chorus stacks on hooks",
            )
        elif backing_vocal_gender == "m":
            base = _append_unique(
                base,
                "male backing vocals, layered male harmonies, chorus stacks",
            )
        else:
            base = _append_unique(
                base,
                "layered backing vocals, rich vocal harmonies, chorus vocal stacks",
            )

    if not plan.instrumental:
        base = ensure_russian_vocal_style(base)

    from backend.utils.suno_payload import compact_suno_style

    return compact_suno_style(base or "modern commercial production")
