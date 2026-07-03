from backend.models import MusicAnalysis, ProductionPlan, SunoPromptPayload
from backend.services.ai_music_analyst import AiMusicAnalyst
from backend.services.ai_prompt_composer import AiPromptComposer
from backend.services.idea_parser import merge_parsed_with_request, parse_idea
from backend.services.reference_translator import ReferenceTranslator
from backend.services.plan_overrides import apply_user_to_plan
from backend.services.style_enforcer import enforce_style
from backend.services.yandex_client import YandexClient
from backend.logger import log
from backend.utils.text import (
    clean_text,
    ensure_russian_vocal_style,
    lyrics_look_lazy,
    scrub_idea_echo_from_lyrics,
    truncate,
)


class PromptBuilder:
    LYRICS_SYSTEM = (
        "Ты профессиональный поэт-песенник для музыкального сервиса. "
        "Напиши полноценный художественный текст песни на русском языке. "
        "Обязательная структура с тегами на английском: "
        "[Verse 1], [Chorus], [Verse 2], [Chorus], [Bridge], [Chorus], [Outro]. "
        "В каждом куплете 4 строки с рифмой, в припеве 4 строки. "
        "Запрещено: копировать описание пользователя, пересказывать промпт, "
        "писать прозу вместо стихов, markdown, пояснения. "
        "Бери только тему и настроение — превращай в метафоры и образы."
    )
    LYRICS_RETRY_HINT = (
        "\n\nКРИТИЧНО: нельзя использовать фразы из описания пользователя. "
        "Пиши оригинальные стихи с рифмой, как у профессионального автора песен."
    )

    def __init__(self, yandex: YandexClient) -> None:
        self._yandex = yandex
        self._translator = ReferenceTranslator(yandex)
        self._analyst = AiMusicAnalyst(yandex)
        self._composer = AiPromptComposer(yandex)

    def build(
        self,
        idea: str,
        *,
        genre: str = "",
        mood: str = "",
        artist_ref: str = "",
        instrumental: bool = False,
        vocal_hint: str = "",
        backing_vocal: bool = False,
        style_mode: str = "presets",
        custom_description: str = "",
    ) -> tuple[ProductionPlan, SunoPromptPayload]:
        """Parse idea → Reference → Analyst → Composer → Suno payload."""
        parsed = parse_idea(idea)
        (
            genre,
            mood,
            artist_ref,
            vocal_hint,
            backing_vocal,
            backing_gender,
            parsed,
        ) = merge_parsed_with_request(
            parsed,
            genre=genre,
            mood=mood,
            artist_ref=artist_ref,
            vocal_hint=vocal_hint,
            backing_vocal=backing_vocal,
        )

        reference = (
            self._translator.translate(artist_ref, idea=idea)
            if artist_ref.strip()
            else None
        )

        ui_genre_locked = bool(genre.strip())
        ui_artist_locked = bool(artist_ref.strip())
        analysis = self._analyst.analyze(
            idea,
            genre=genre,
            mood=mood,
            reference=reference,
            instrumental=instrumental,
            vocal_hint=vocal_hint,
            backing_vocal=backing_vocal,
            style_mode=style_mode,
            custom_description=custom_description,
            locked_genre=parsed.has_locked_genre or ui_genre_locked,
            locked_artist=parsed.has_locked_artist or ui_artist_locked,
        )
        payload = self._composer.compose(
            analysis,
            idea,
            reference=reference,
            vocal_hint=vocal_hint,
            backing_vocal=backing_vocal,
            backing_vocal_gender=backing_gender,
        )
        plan = self._analysis_to_plan(analysis, payload, parsed=parsed)
        plan = apply_user_to_plan(
            plan,
            genre=genre,
            mood=mood,
            vocal_hint=vocal_hint,
            backing_vocal=backing_vocal,
        )

        payload.style = enforce_style(
            payload.style,
            plan,
            reference=reference,
            backing_vocal=backing_vocal,
            backing_vocal_gender=backing_gender,
        )
        payload.vocal_gender = plan.vocal_gender
        payload.negative_tags = plan.negative_tags
        payload.style_weight = plan.style_weight
        payload.weirdness_constraint = plan.weirdness_constraint
        payload.audio_weight = plan.audio_weight

        if plan.instrumental:
            payload.lyrics = ""
        else:
            payload.lyrics = self.generate_lyrics(idea, plan)

        return plan, payload

    def build_plan(
        self,
        idea: str,
        *,
        genre: str = "",
        mood: str = "",
        artist_ref: str = "",
        instrumental: bool = False,
        vocal_hint: str = "",
        backing_vocal: bool = False,
        style_mode: str = "presets",
        custom_description: str = "",
    ) -> ProductionPlan:
        plan, _ = self.build(
            idea,
            genre=genre,
            mood=mood,
            artist_ref=artist_ref,
            instrumental=instrumental,
            vocal_hint=vocal_hint,
            backing_vocal=backing_vocal,
            style_mode=style_mode,
            custom_description=custom_description,
        )
        return plan

    def generate_lyrics(self, idea: str, plan: ProductionPlan) -> str:
        lyrics, source = self._generate_lyrics_with_source(idea, plan)
        log.info(
            "Lyrics generated via %s (len=%s, lazy=%s)",
            source,
            len(lyrics),
            lyrics_look_lazy(lyrics, idea),
        )
        return lyrics

    def _generate_lyrics_with_source(
        self, idea: str, plan: ProductionPlan
    ) -> tuple[str, str]:
        if plan.instrumental:
            return "", "instrumental"

        user_text = self._lyrics_user_prompt(idea, plan)
        attempts: list[tuple[str, float, str, str]] = [
            (self._yandex.MODEL_PRO, 0.72, "", "yandexgpt"),
            (self._yandex.MODEL_PRO, 0.88, self.LYRICS_RETRY_HINT, "yandexgpt-retry"),
            (self._yandex.MODEL_LITE, 0.82, self.LYRICS_RETRY_HINT, "yandexgpt-lite-retry"),
        ]

        for model, temperature, extra_hint, source in attempts:
            try:
                lyrics = clean_text(
                    self._yandex.complete(
                        self.LYRICS_SYSTEM,
                        user_text + extra_hint,
                        max_tokens=1000,
                        temperature=temperature,
                        model=model,
                    )
                )
                lyrics = scrub_idea_echo_from_lyrics(lyrics, idea)
                if lyrics and not lyrics_look_lazy(lyrics, idea):
                    return lyrics, source
                log.info("Lyrics attempt %s looked lazy — next try", source)
            except Exception:
                log.exception("Lyrics attempt %s failed", source)

        log.warning("All lyrics attempts failed — using template fallback")
        return self._fallback_lyrics(idea), "template-fallback"

    @staticmethod
    def _lyrics_user_prompt(idea: str, plan: ProductionPlan) -> str:
        return (
            f"Тема песни (не копировать дословно): {idea}\n"
            f"Жанр: {plan.genre} / {plan.subgenre}\n"
            f"Настроение: {plan.mood}\n"
            f"Энергия: {plan.energy}\n"
            f"BPM: {plan.bpm}\n"
            f"Вокал: {plan.vocal} — {plan.vocal_description}\n"
            f"Атмосфера: {plan.atmosphere}\n"
            f"Структура: {plan.structure}"
        )

    def build_style(self, plan: ProductionPlan) -> str:
        instruments = ", ".join(plan.instruments)
        parts = [
            f"{plan.genre} {plan.subgenre}",
            f"{plan.mood} mood",
            f"{plan.bpm} BPM",
            f"{plan.energy} energy",
            instruments,
            plan.vocal_description,
            plan.production_style,
            plan.atmosphere,
            "crystal clear mix",
            "commercial production",
        ]
        if plan.vocal == "duet":
            parts.append("male and female duet vocals")
        style = ", ".join(p for p in parts if p)
        if not plan.instrumental:
            style = ensure_russian_vocal_style(style)
        return truncate(style, 950)

    def build_style_via_ai(
        self,
        plan: ProductionPlan,
        artist_ref: str = "",
        *,
        style_mode: str = "presets",
        custom_description: str = "",
    ) -> str:
        artist_part = ""
        if artist_ref.strip():
            reference = self._translator.translate(artist_ref)
            if reference.has_content:
                artist_part = (
                    f"Референс звучания (без имён артистов): {reference.style_tags}. "
                )
            else:
                artist_part = (
                    f"Референс (без имён артистов в ответе): {artist_ref.strip()}. "
                )
        custom_part = ""
        if style_mode == "custom" and custom_description.strip():
            custom_part = (
                f"Пользователь описал звучание своими словами: "
                f"{custom_description.strip()}. "
            )

        system_prompt = (
            "Ты эксперт по музыкальному продакшену для Suno V5.5. "
            "Собери профессиональный style prompt на английском: жанр, поджанр, "
            "настроение, BPM, энергия, инструменты, вокал, продакшн, атмосфера, микс. "
            "Обязательно укажи sung in Russian и native Russian vocals. "
            "Одна строка через запятую, без имён артистов, максимум 900 символов."
        )
        user_text = (
            f"{custom_part}"
            f"{artist_part}"
            f"Genre: {plan.genre}, Subgenre: {plan.subgenre}, Mood: {plan.mood}, "
            f"BPM: {plan.bpm}, Energy: {plan.energy}, Vocal: {plan.vocal}, "
            f"Instruments: {', '.join(plan.instruments)}, "
            f"Production: {plan.production_style}, Atmosphere: {plan.atmosphere}"
        )
        try:
            style = self._yandex.complete(
                system_prompt,
                user_text,
                max_tokens=250,
                temperature=0.55,
            )
            style = clean_text(style)
            if style:
                if not plan.instrumental:
                    style = ensure_russian_vocal_style(style)
                return truncate(style, 950)
        except Exception:
            pass
        return self.build_style(plan)

    @staticmethod
    def _build_explanation(parsed) -> str:
        parts = ["AI-продюсер разобрал вашу идею."]
        if parsed.has_locked_genre:
            parts.append(f"Жанр из текста: {parsed.genre}.")
        if parsed.has_locked_artist:
            parts.append(f"Референс: {parsed.artist_ref}.")
        if parsed.mood:
            parts.append(f"Настроение: {parsed.mood}.")
        if parsed.backing_vocal:
            gender = (
                "женские"
                if parsed.backing_vocal_gender == "f"
                else "мужские"
                if parsed.backing_vocal_gender == "m"
                else ""
            )
            parts.append(f"Подпевки: {gender or 'да'}.")
        if parsed.vocal_hint:
            parts.append(f"Лид-вокал: {parsed.vocal_hint}.")
        return " ".join(parts)

    @staticmethod
    def _analysis_to_plan(
        analysis: MusicAnalysis,
        payload: SunoPromptPayload,
        *,
        parsed=None,
    ) -> ProductionPlan:
        explanation = (
            PromptBuilder._build_explanation(parsed)
            if parsed and parsed.locked_fields
            else "AI-продюсер анализирует идею и подбирает оптимальные параметры генерации."
        )
        return ProductionPlan(
            genre=analysis.genre,
            subgenre=analysis.subgenre,
            mood=analysis.mood,
            bpm=analysis.bpm,
            energy=analysis.energy,
            instruments=analysis.instruments,
            atmosphere=analysis.atmosphere,
            production_style=analysis.production_style,
            vocal=analysis.vocal,
            vocal_description=analysis.vocal_description,
            structure=analysis.structure,
            negative_tags=payload.negative_tags,
            style_weight=payload.style_weight,
            weirdness_constraint=payload.weirdness_constraint,
            audio_weight=payload.audio_weight,
            vocal_gender=payload.vocal_gender,
            instrumental=analysis.instrumental,
            explanation_ru=explanation,
            optimized_idea=analysis.idea,
        )

    @staticmethod
    def _fallback_plan(
        idea: str,
        *,
        instrumental: bool = False,
        vocal_hint: str = "",
    ) -> ProductionPlan:
        vocal = vocal_hint if vocal_hint in {"male", "female", "duet", "auto"} else "auto"
        return ProductionPlan(
            genre="Pop",
            subgenre="Modern Pop",
            mood="uplifting",
            bpm=120,
            energy="medium",
            instruments=["synth", "drums", "bass", "electric guitar"],
            atmosphere="modern emotional atmosphere",
            production_style="radio-ready polished mix",
            vocal=vocal,
            vocal_description="expressive modern vocals",
            explanation_ru="Подобрали универсальный поп-стиль под вашу идею.",
            instrumental=instrumental,
            optimized_idea=idea,
        )

    @staticmethod
    def _fallback_lyrics(idea: str) -> str:
        return (
            "[Verse 1]\n"
            "В сердце тихо тает лёд\n"
            "Город дышит в синий час\n"
            "Я ищу свой новый след\n"
            "Среди звёзд и между нас\n\n"
            "[Chorus]\n"
            "Это песня — мой огонь\n"
            "Звучит внутри и снаружи\n"
            "Каждый такт ведёт домой\n"
            "Туда, где слышны только чувства\n\n"
            "[Verse 2]\n"
            "Каждый бит — как новый день\n"
            "Я иду туда, где слышен свет\n"
            "Пусть мелодия звенит\n"
            "И не знает больше преград\n\n"
            "[Chorus]\n"
            "Это песня — мой огонь\n"
            "Звучит внутри и снаружи\n\n"
            "[Outro]\n"
            "Навсегда."
        )