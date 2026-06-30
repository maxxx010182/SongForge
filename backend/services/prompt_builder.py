from backend.models import MusicAnalysis, ProductionPlan, SunoPromptPayload
from backend.services.ai_music_analyst import AiMusicAnalyst
from backend.services.ai_prompt_composer import AiPromptComposer
from backend.services.reference_translator import ReferenceTranslator
from backend.services.yandex_client import YandexClient
from backend.utils.text import clean_text, ensure_russian_vocal_style, truncate


class PromptBuilder:
    LYRICS_SYSTEM = (
        "Ты поэт-песенник и музыкальный продюсер. "
        "Напиши текст песни на русском языке со структурными тегами "
        "[Verse 1], [Chorus], [Verse 2], [Chorus], [Bridge], [Chorus], [Outro]. "
        "Только текст песни, без пояснений и markdown."
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
        """Reference → Analyst → Composer → Suno payload."""
        reference = self._translator.translate(artist_ref, idea=idea) if artist_ref.strip() else None

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
        )
        payload = self._composer.compose(
            analysis,
            idea,
            reference=reference,
            vocal_hint=vocal_hint,
            backing_vocal=backing_vocal,
        )
        plan = self._analysis_to_plan(analysis, payload)
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
        if plan.instrumental:
            return ""

        user_text = (
            f"Идея: {idea}\n"
            f"Жанр: {plan.genre} / {plan.subgenre}\n"
            f"Настроение: {plan.mood}\n"
            f"Энергия: {plan.energy}\n"
            f"BPM: {plan.bpm}\n"
            f"Вокал: {plan.vocal} — {plan.vocal_description}\n"
            f"Атмосфера: {plan.atmosphere}\n"
            f"Структура: {plan.structure}"
        )
        try:
            lyrics = self._yandex.complete(
                self.LYRICS_SYSTEM,
                user_text,
                max_tokens=700,
                temperature=0.75,
            )
            return clean_text(lyrics)
        except Exception:
            return self._fallback_lyrics(idea)

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
    def _analysis_to_plan(
        analysis: MusicAnalysis,
        payload: SunoPromptPayload,
    ) -> ProductionPlan:
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
            explanation_ru="AI-продюсер анализирует идею и подбирает оптимальные параметры генерации.",
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
        snippet = truncate(idea, 80)
        return (
            f"[Verse 1]\n{snippet}\nМузыка ведёт меня вперёд\n\n"
            f"[Chorus]\nЭто моя песня, мой огонь\n"
            f"Звучит внутри и снаружи\n\n"
            f"[Verse 2]\nКаждый бит — как новый день\n"
            f"Я иду туда, где слышен свет\n\n"
            f"[Chorus]\nЭто моя песня, мой огонь\n"
            f"Звучит внутри и снаружи\n\n"
            f"[Outro]\nНавсегда."
        )