"""Supplement AI-generated Suno style prompts — never replace the AI output."""

from backend.models import ProductionPlan
from backend.services.reference_translator import ReferenceTranslation
from backend.utils.text import clean_text, ensure_russian_vocal_style, truncate

_MIN_STYLE_LEN = 80


def _contains(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()


def _append_unique(style: str, fragment: str) -> str:
    fragment = fragment.strip()
    if not fragment or _contains(style, fragment):
        return style
    if style.strip():
        return f"{style}, {fragment}"
    return fragment


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

    if plan.vocal == "duet":
        base = _append_unique(
            base,
            "male and female duet vocals, dual lead vocals, "
            "alternating male and female verses",
        )
    elif plan.vocal == "male":
        base = _append_unique(base, "male lead vocals")
    elif plan.vocal == "female":
        base = _append_unique(base, "female lead vocals")

    if backing_vocal:
        base = _append_unique(
            base,
            "layered backing vocals, rich vocal harmonies, chorus vocal stacks",
        )

    if not plan.instrumental:
        base = ensure_russian_vocal_style(base)

    return truncate(base or "modern commercial production", 950)