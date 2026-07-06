"""Общие поля запроса Suno для ApiPass и sunoapi.org."""

from __future__ import annotations

from typing import Any, Optional

from backend.models import ProductionPlan
from backend.utils.suno_payload import (
    clamp_suno_prompt,
    compact_suno_style,
    sanitize_negative_tags,
    sanitize_suno_title,
)
from backend.utils.text import clean_text


def vocal_gender_for_plan(plan: ProductionPlan) -> Optional[str]:
    if plan.vocal == "duet":
        return None
    gender = (plan.vocal_gender or "").strip().lower()
    if gender in {"m", "f"}:
        return gender
    if plan.vocal == "male":
        return "m"
    if plan.vocal == "female":
        return "f"
    return None


def build_suno_custom_payload(
    *,
    lyrics: str,
    style: str,
    title: str,
    plan: ProductionPlan,
) -> dict[str, Any]:
    prompt = "" if plan.instrumental else clamp_suno_prompt(clean_text(lyrics))
    safe_style = compact_suno_style(style)
    safe_title = sanitize_suno_title(
        title,
        idea=plan.optimized_idea or (lyrics[:300] if lyrics else title),
    )
    safe_negative = sanitize_negative_tags(
        plan.negative_tags, safe_style, plan.genre
    )

    payload: dict[str, Any] = {
        "customMode": True,
        "instrumental": plan.instrumental,
        "prompt": prompt,
        "style": safe_style,
        "title": safe_title,
        "negativeTags": safe_negative,
        "styleWeight": plan.style_weight,
        "weirdnessConstraint": plan.weirdness_constraint,
        "audioWeight": plan.audio_weight,
    }

    vocal_gender = vocal_gender_for_plan(plan)
    if vocal_gender:
        payload["vocalGender"] = vocal_gender

    return payload