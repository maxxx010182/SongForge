"""Apply explicit user choices to analysis/plan — no circular imports."""

from backend.models import MusicAnalysis, ProductionPlan
from backend.services.genre_resolver import resolve_genre

_MOOD_ENERGY: dict[str, str] = {
    "romantic": "medium",
    "uplifting": "high",
    "melancholy": "low",
    "melancholic": "low",
    "dark": "high",
    "joyful": "high",
    "peaceful": "low",
    "calm": "low",
    "angry": "high",
    "nostalgic": "medium",
    "party": "high",
    "spiritual": "medium",
    "experimental": "medium",
    "adventurous": "high",
    "epic": "high",
}

_GENRE_ANTI_POP: dict[str, str] = {
    "hip-hop": "upbeat pop, cheerful pop, bright pop, dance pop, euro pop, bubblegum pop",
    "hip hop": "upbeat pop, cheerful pop, bright pop, dance pop, euro pop",
    "rock": "cheerful pop, bubblegum pop, soft pop ballad",
    "metal": "soft pop, acoustic pop, cheerful pop",
    "r&b": "cheerful euro pop, bubblegum pop",
}


def apply_user_to_analysis(
    analysis: MusicAnalysis,
    *,
    genre: str = "",
    mood: str = "",
    vocal_hint: str = "",
) -> MusicAnalysis:
    if genre.strip():
        genre_en, subgenre = resolve_genre(genre, "")
        analysis.genre = genre_en
        analysis.subgenre = subgenre

    if mood.strip():
        mood_key = mood.strip().lower()
        analysis.mood = mood_key
        analysis.energy = _MOOD_ENERGY.get(mood_key, analysis.energy)

    if vocal_hint in {"male", "female", "duet", "auto"}:
        analysis.vocal = vocal_hint
        if vocal_hint == "duet":
            analysis.vocal_description = (
                "male and female duet vocals, alternating lead lines"
            )
        elif vocal_hint == "male":
            analysis.vocal_description = "male lead vocals"
        elif vocal_hint == "female":
            analysis.vocal_description = "female lead vocals"

    return analysis


def apply_user_to_plan(
    plan: ProductionPlan,
    *,
    genre: str = "",
    mood: str = "",
    vocal_hint: str = "",
    backing_vocal: bool = False,
) -> ProductionPlan:
    if genre.strip():
        genre_en, subgenre = resolve_genre(genre, "")
        plan.genre = genre_en
        plan.subgenre = subgenre

    if mood.strip():
        plan.mood = mood.strip().lower()
        plan.energy = _MOOD_ENERGY.get(plan.mood, plan.energy)

    if vocal_hint in {"male", "female", "duet", "auto"}:
        plan.vocal = vocal_hint

    if plan.vocal == "duet":
        plan.vocal_gender = ""
    elif plan.vocal == "male":
        plan.vocal_gender = "m"
        plan.negative_tags = _append_negative(
            plan.negative_tags,
            "solo female lead, female lead only, pop ballad vocals",
        )
    elif plan.vocal == "female":
        plan.vocal_gender = "f"

    if backing_vocal:
        plan.negative_tags = _append_negative(
            plan.negative_tags,
            "a cappella, dry solo vocal, no backing vocals, no harmonies",
        )

    if plan.vocal == "duet":
        plan.negative_tags = _append_negative(
            plan.negative_tags,
            "solo female only, solo male only, single vocalist, one voice only",
        )

    genre_key = plan.genre.lower()
    anti = _GENRE_ANTI_POP.get(genre_key) or _GENRE_ANTI_POP.get(
        genre_key.replace("-", " ")
    )
    if anti:
        plan.negative_tags = _append_negative(plan.negative_tags, anti)

    return plan


def _append_negative(existing: str, extra: str) -> str:
    if not extra.strip():
        return existing
    if extra.lower() in existing.lower():
        return existing
    if existing.strip():
        return f"{existing}, {extra}"
    return extra