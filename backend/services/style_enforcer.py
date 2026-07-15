"""Supplement AI-generated Suno style prompts — never replace the AI output."""

import re

from backend.models import ProductionPlan
from backend.services.idea_parser import is_rap_genre
from backend.services.reference_translator import ReferenceTranslation
from backend.utils.text import clean_text, ensure_russian_vocal_style, truncate

_MIN_STYLE_LEN = 80

# Если жанр hip-hop/rap — вычищаем «Modern Pop» из style (Yandex часто подмешивает).
_POP_LEAK_RE = re.compile(
    r",?\s*\b(?:"
    r"modern\s+pop|upbeat\s+pop|cheerful\s+pop|bright\s+pop|dance\s+pop|"
    r"euro\s+pop|bubblegum\s+pop|pop\s+rock|synth[\s-]?pop|"
    r"powerful\s+melodic\s+vocals|radio[\s-]?ready\s+polished\s+mix"
    r")\b\s*,?",
    re.IGNORECASE,
)


def _contains(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()


def _append_unique(style: str, fragment: str) -> str:
    fragment = fragment.strip()
    if not fragment or _contains(style, fragment):
        return style
    if style.strip():
        return f"{style}, {fragment}"
    return fragment


def _strip_pop_leak_for_rap(style: str) -> str:
    cleaned = _POP_LEAK_RE.sub(", ", style)
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


def enforce_style(
    style: str,
    plan: ProductionPlan,
    *,
    reference: ReferenceTranslation | None = None,
    backing_vocal: bool = False,
    backing_vocal_gender: str = "",
) -> str:
    """Keep AI style as the base; prepend reference and append only missing tags."""
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

    genre_line = f"{plan.genre} {plan.subgenre}".strip()
    if genre_line:
        base = _append_unique(base, genre_line)
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

    if is_rap_genre(plan.genre, plan.subgenre):
        base = _strip_pop_leak_for_rap(base)
        # Жанр в начало — Suno сильнее опирается на первые теги style
        rap_head = "Russian hip-hop, rap vocals, 808 drums, boom bap flow, urban beat"
        if not _contains(base, "hip-hop") and not _contains(base, "rap vocal"):
            base = f"{rap_head}, {base}" if base else rap_head
        else:
            base = _append_unique(base, rap_head)
        atmosphere = (plan.atmosphere or "").lower()
        if plan.energy == "high" or any(
            t in atmosphere for t in ("stadium", "live", "concert", "crowd", "arena")
        ):
            base = _append_unique(
                base, "live stadium energy, concert atmosphere, crowd singalong hooks"
            )

    if plan.vocal == "duet":
        base = _append_unique(
            base,
            "male and female duet vocals, dual lead vocals, "
            "alternating male and female verses, male rap verses with female sung hook",
        )
    elif plan.vocal == "male":
        base = _append_unique(base, "male lead vocals, deep male rap delivery")
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