"""Единый генератор title + lyrics + style для custom vocal (режим unified)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.logger import log
from backend.models import MusicAnalysis
from backend.services.reference_translator import ReferenceTranslation
from backend.services.lyrics_craft_prompt import (
    UNIFIED_MODEL_ATTEMPTS,
    UNIFIED_PACKAGE_SYSTEM,
    UNIFIED_SCREENPLAY_RETRY_HINT,
)
from backend.services.yandex_client import YandexClient
from backend.utils.suno_payload import (
    SUNO_STYLE_MAX_LEN,
    clamp_suno_prompt,
    compact_suno_style,
    sanitize_suno_title,
)
from backend.utils.text import (
    clean_text,
    ensure_russian_vocal_style,
    extract_json,
    lyrics_language_instruction,
    lyrics_look_english,
    lyrics_look_lazy,
    resolve_lyrics_language,
    scrub_idea_echo_from_lyrics,
)

@dataclass
class SunoPackageResult:
    title: str
    lyrics: str
    style: str
    source: str = "unified"


def _lyrics_retry_hint(idea: str) -> str:
    return f"\n\nКРИТИЧНО: {lyrics_language_instruction(idea)}"


class SunoPackageComposer:
    def __init__(self, yandex: YandexClient) -> None:
        self._yandex = yandex

    def compose(
        self,
        idea: str,
        analysis: MusicAnalysis,
        *,
        reference: ReferenceTranslation | None = None,
        vocal_hint: str = "",
        backing_vocal: bool = False,
        backing_vocal_gender: str = "",
        custom_description: str = "",
    ) -> SunoPackageResult | None:
        user_text = self._build_user_prompt(
            idea,
            analysis,
            reference=reference,
            vocal_hint=vocal_hint,
            backing_vocal=backing_vocal,
            backing_vocal_gender=backing_vocal_gender,
            custom_description=custom_description,
        )
        lang_code, _, _ = resolve_lyrics_language(idea)
        retry_hint = _lyrics_retry_hint(idea)
        for model_name, temperature, suffix in UNIFIED_MODEL_ATTEMPTS:
            model = (
                self._yandex.MODEL_PRO
                if model_name == self._yandex.MODEL_PRO
                else self._yandex.MODEL_LITE
            )
            label = f"unified-{model_name}" + (f"-{suffix}" if suffix else "")
            extra_hint = ""
            if suffix:
                extra_hint = UNIFIED_SCREENPLAY_RETRY_HINT + retry_hint
            try:
                raw = self._yandex.complete(
                    UNIFIED_PACKAGE_SYSTEM,
                    user_text + extra_hint,
                    model=model,
                    max_tokens=2400,
                    temperature=temperature,
                )
                result = self._parse_response(
                    raw,
                    idea=idea,
                    analysis=analysis,
                )
                if not result or lyrics_look_lazy(result.lyrics, idea):
                    log.warning("Unified package %s: lazy or empty lyrics", label)
                    continue
                if lang_code == "ru" and lyrics_look_english(result.lyrics):
                    log.warning("Unified package %s: expected Russian lyrics — retry", label)
                    continue
                result.source = label
                return result
            except Exception:
                log.exception("Unified package attempt %s failed", label)
        return None

    @staticmethod
    def _build_user_prompt(
        idea: str,
        analysis: MusicAnalysis,
        *,
        reference: ReferenceTranslation | None = None,
        vocal_hint: str = "",
        backing_vocal: bool = False,
        backing_vocal_gender: str = "",
        custom_description: str = "",
    ) -> str:
        parts = [
            f"Описание от пользователя: {idea}",
            f"Жанр: {analysis.genre} / {analysis.subgenre}",
            f"Настроение: {analysis.mood}",
            f"BPM: {analysis.bpm}",
            f"Энергия: {analysis.energy}",
            f"Вокал: {analysis.vocal} — {analysis.vocal_description}",
            f"Инструменты: {', '.join(analysis.instruments)}",
            f"Атмосфера: {analysis.atmosphere}",
            f"Продакшн: {analysis.production_style}",
            f"Структура: {analysis.structure}",
        ]
        if custom_description.strip():
            parts.append(
                f"Пользователь описал звучание: {custom_description.strip()}"
            )
        if reference and reference.has_content:
            parts.append(
                f"Референс звучания (без имён): {reference.style_tags}"
            )
            if reference.vocal_description:
                parts.append(f"Характер вокала референса: {reference.vocal_description}")
        if vocal_hint == "duet" or analysis.vocal == "duet":
            parts.append("Обязательно: мужской и женский вокал в одном треке.")
        if backing_vocal:
            gender = (
                "женские"
                if backing_vocal_gender == "f"
                else "мужские"
                if backing_vocal_gender == "m"
                else ""
            )
            parts.append(
                f"Обязательно: подпевки ({gender or 'любые'}), гармонии на припеве."
            )
        energy = (analysis.energy or "").lower()
        genre_blob = f"{analysis.genre} {analysis.subgenre} {analysis.mood}".lower()
        if any(
            token in idea.lower()
            for token in ("стадион", "stadium", "концерт", "arena", "толпа", "live")
        ) or any(
            token in genre_blob
            for token in ("rap", "rock", "pop", "stadium", "anthem", "party")
        ) or energy in ("high", "very high", "энергич"):
            parts.append(
                "Энергичный трек: добавь в lyrics crowd/stadium-теги, ad-libs и "
                "нарастание к финальному припеву, если уместно теме."
            )
        parts.append(lyrics_language_instruction(idea))
        return "\n".join(parts)

    @staticmethod
    def _parse_response(
        raw: str,
        *,
        idea: str,
        analysis: MusicAnalysis,
    ) -> SunoPackageResult | None:
        data = extract_json(raw)
        title = clean_text(str(data.get("title", ""))).strip("\"'«»")
        lyrics = clean_text(
            str(data.get("lyrics") or data.get("prompt") or "")
        )
        style = clean_text(
            str(data.get("style_prompt") or data.get("style") or "")
        )

        if not lyrics.strip() or not style.strip():
            return None

        lyrics = scrub_idea_echo_from_lyrics(lyrics, idea)
        lyrics = SunoPackageComposer._ensure_structure_start(lyrics)
        lyrics = clamp_suno_prompt(lyrics)
        if len(lyrics) < 80:
            return None

        style = ensure_russian_vocal_style(style)
        style = compact_suno_style(style, max_len=SUNO_STYLE_MAX_LEN)
        if not style:
            return None

        safe_title = sanitize_suno_title(title, idea=idea or analysis.idea)
        return SunoPackageResult(title=safe_title, lyrics=lyrics, style=style)

    @staticmethod
    def _ensure_structure_start(lyrics: str) -> str:
        text = lyrics.strip()
        if not text:
            return text
        first = text.splitlines()[0].strip().lower()
        if first.startswith(
            ("[verse", "[chorus", "[intro", "[pre-chorus", "[bridge", "[outro", "[crowd")
        ):
            return text
        return f"[Verse 1]\n{text}"