"""Единый генератор title + lyrics + style для custom vocal (режим unified)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.logger import log
from backend.models import MusicAnalysis
from backend.services.reference_translator import ReferenceTranslation
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
    idea_looks_russian,
    lyrics_look_english,
    lyrics_look_lazy,
    scrub_idea_echo_from_lyrics,
)

_SYSTEM = (
    "Ты — профессиональный автор текстов песен и саунд-продюсер для музыкального "
    "сервиса (custom vocal: отдельно lyrics, title и style). "
    "Верни ТОЛЬКО валидный JSON без markdown. "
    'Поля: "title" (короткое название на русском, 1–4 слова, НЕ сценическая ремарка), '
    '"lyrics" (полный текст песни: строки куплетов и припева ТОЛЬКО на русском; '
    "структурные теги [Verse 1], [Chorus], [Bridge], [Outro] — на английском), "
    '"style_prompt" (одна строка на английском через запятую). '
    "title: максимум 60 символов, без скобок-ремарок. "
    "lyrics: первая строка — структурный тег ([Verse 1]); сценические теги "
    "([Crowd cheering], [Female backing vocals]) только внутри блоков; "
    "куплеты до 4 строк; припев короткий и запоминающийся; весь текст до 2800 символов. "
    "ЗАПРЕЩЕНО писать куплеты и припев на английском, если запрос пользователя на русском. "
    "style_prompt: 12–20 слов И не более 180 символов; обязательно "
    "sung in Russian, native Russian vocals; жанр, вокал, инструменты, атмосфера, "
    "1–2 продакшн-детали; без имён артистов; без дублей."
)


@dataclass
class SunoPackageResult:
    title: str
    lyrics: str
    style: str
    source: str = "unified"


_RUSSIAN_LYRICS_RETRY = (
    "\n\nКРИТИЧНО: запрос на русском. Поле lyrics — строки песни только на русском. "
    "Английский допустим только в тегах [Verse 1], [Chorus], [Bridge], [Outro]."
)


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
        require_russian = idea_looks_russian(idea)
        for model, temperature, label, extra_hint in (
            (self._yandex.MODEL_PRO, 0.72, "unified-pro", ""),
            (self._yandex.MODEL_PRO, 0.62, "unified-pro-ru", _RUSSIAN_LYRICS_RETRY),
            (self._yandex.MODEL_LITE, 0.65, "unified-lite-ru", _RUSSIAN_LYRICS_RETRY),
        ):
            try:
                raw = self._yandex.complete(
                    _SYSTEM,
                    user_text + extra_hint,
                    model=model,
                    max_tokens=2200,
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
                if require_russian and lyrics_look_english(result.lyrics):
                    log.warning("Unified package %s: lyrics in English — retry", label)
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
        if any(
            token in idea.lower()
            for token in ("стадион", "stadium", "концерт", "arena", "толпа", "live")
        ):
            parts.append(
                "Нужна живая/стадионная атмосфера — добавь уместные crowd-теги в lyrics."
            )
        if idea_looks_russian(idea):
            parts.append(
                "ОБЯЗАТЕЛЬНО: текст песни (куплеты, припев, бридж) только на русском языке."
            )
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
        lyrics = clean_text(str(data.get("lyrics", "")))
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
        if first.startswith("[verse") or first.startswith("[chorus"):
            return text
        return f"[Verse 1]\n{text}"