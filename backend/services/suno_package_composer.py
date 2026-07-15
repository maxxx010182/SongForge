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
    lyrics_screenplay_user_hint,
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
    lyrics_look_incomplete,
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
                    max_tokens=3500,
                    temperature=temperature,
                )
                result = self._parse_response(
                    raw,
                    idea=idea,
                    analysis=analysis,
                )
                if not result:
                    log.warning("Unified package %s: empty/unparseable", label)
                    continue
                if lyrics_look_lazy(result.lyrics, idea):
                    log.warning(
                        "Unified package %s: lazy lyrics (len=%s)",
                        label,
                        len(result.lyrics),
                    )
                    continue
                if lyrics_look_incomplete(result.lyrics, idea):
                    log.warning(
                        "Unified package %s: incomplete structure/len (len=%s)",
                        label,
                        len(result.lyrics),
                    )
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
            f"БРИФ (не готовый текст — преврати в песню): {idea}",
            "Задача: полная песня ~4 минуты, качественный сонграйтинг, "
            "НЕ пересказ брифа «что вижу — то пою».",
            f"Жанр: {analysis.genre} / {analysis.subgenre} "
            f"(style_prompt ОБЯЗАН совпадать с ЭТИМ жанром — Jazz≠Pop, Rock≠Hip-Hop, "
            f"Ballad≠Metal; не подменяй жанр «удобным» Modern Pop)",
            f"Настроение: {analysis.mood}",
            f"BPM: {analysis.bpm}",
            f"Энергия: {analysis.energy}",
            f"Вокал: {analysis.vocal} — {analysis.vocal_description}",
            f"Инструменты: {', '.join(analysis.instruments)}",
            f"Атмосфера: {analysis.atmosphere}",
            f"Продакшн: {analysis.production_style}",
            f"Ориентир структуры: {analysis.structure}",
            "Обязательная форма lyrics: Verse1 → Pre → Chorus → Verse2 → Pre → "
            "Chorus → Bridge → Final Chorus → Outro; припев дословно одинаков; "
            "lyrics 2000–4500 символов (если не детская).",
            "style_prompt: СНАЧАЛА точные English-теги жанра/поджанра из строки выше, "
            "потом mood, instruments, vocals, production; без чужого жанра.",
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
        parts.append(
            lyrics_screenplay_user_hint(
                genre=analysis.genre,
                subgenre=analysis.subgenre,
                mood=analysis.mood,
                energy=analysis.energy,
                idea=idea,
                backing_vocal=backing_vocal,
            )
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
        # Короткий «скелет» отсекаем на compose(); здесь только явный мусор.

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
        # Режиссура вроде [Crowd …] — не вокальная секция; нужен [Verse 1] в начале.
        if first.startswith(
            (
                "[verse",
                "[chorus",
                "[intro",
                "[pre-chorus",
                "[bridge",
                "[outro",
                "[final chorus",
                "[build",
                "[drop",
                "[breakdown",
            )
        ):
            return text
        return f"[Verse 1]\n{text}"