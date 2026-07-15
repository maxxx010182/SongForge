from backend.models import MusicAnalysis, ProductionPlan, SunoPromptPayload
from backend.services.ai_music_analyst import AiMusicAnalyst
from backend.services.ai_prompt_composer import AiPromptComposer
from backend.services.idea_parser import merge_parsed_with_request, parse_idea
from backend.services.lyrics_craft_prompt import (
    CLASSIC_LYRICS_RETRY_HINT,
    CLASSIC_LYRICS_SYSTEM,
    LYRICS_MODEL_ATTEMPTS,
    lyrics_screenplay_user_hint,
)
from backend.services.suno_package_composer import SunoPackageComposer
from backend.services.reference_translator import ReferenceTranslator
from backend.services.plan_overrides import apply_user_to_plan
from backend.services.style_enforcer import enforce_style
from backend.services.llm_factory import LlmClient
from backend.logger import log
from backend.utils.suno_payload import (
    compact_suno_style,
    sanitize_negative_tags,
    sanitize_suno_title,
)
from backend.settings import DEFAULT_AUDIO_WEIGHT, DEFAULT_STYLE_WEIGHT, DEFAULT_WEIRDNESS
from backend.utils.text import (
    clean_text,
    ensure_russian_vocal_style,
    lyrics_language_instruction,
    lyrics_look_english,
    lyrics_look_incomplete,
    lyrics_look_lazy,
    resolve_lyrics_language,
    scrub_idea_echo_from_lyrics,
    truncate,
)


class PromptBuilder:
    def __init__(self, llm: LlmClient) -> None:
        self._yandex = llm  # имя историческое; клиент Yandex или OpenAI-compat
        self._translator = ReferenceTranslator(llm)
        self._analyst = AiMusicAnalyst(llm)
        self._composer = AiPromptComposer(llm)
        self._package = SunoPackageComposer(llm)

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
        lyrics_engine: str = "classic",
    ) -> tuple[ProductionPlan, SunoPromptPayload]:
        """Parse idea → Reference → Analyst → Composer → Suno payload."""
        use_unified = lyrics_engine == "unified" and not instrumental
        custom_mode = style_mode == "custom" and custom_description.strip()
        parse_text = idea.strip()
        if custom_mode:
            parse_text = (
                f"{idea.strip()}\n{custom_description.strip()}".strip()
                if idea.strip()
                else custom_description.strip()
            )
            # Списки жанра/настроения скрыты — не перебивать текст пользователя.
            genre = ""
            mood = ""

        parsed = parse_idea(parse_text or idea)
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

        analyst_idea = parse_text or idea

        reference = (
            self._translator.translate(artist_ref, idea=analyst_idea)
            if artist_ref.strip()
            else None
        )

        ui_genre_locked = bool(genre.strip())
        ui_artist_locked = bool(artist_ref.strip())
        analysis = self._analyst.analyze(
            analyst_idea,
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

        package = None
        if use_unified:
            package = self._package.compose(
                analyst_idea,
                analysis,
                reference=reference,
                vocal_hint=vocal_hint,
                backing_vocal=backing_vocal,
                backing_vocal_gender=backing_gender,
                custom_description=custom_description,
            )

        if package:
            payload = self._payload_from_unified_package(
                package,
                analysis,
                backing_vocal=backing_vocal,
            )
            log.info(
                "Unified lyrics engine: source=%s title=%r style_len=%s lyrics_len=%s",
                package.source,
                payload.title,
                len(payload.style),
                len(payload.lyrics),
            )
        else:
            if use_unified:
                log.warning("Unified engine failed — falling back to classic pipeline")
            payload = self._composer.compose(
                analysis,
                analyst_idea,
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

        # Unified раньше пропускал enforce_style → Yandex мог отдать Modern Pop
        # при идее «жанр реп». Classic уже проходил enforce.
        if custom_mode:
            user_style = truncate(clean_text(custom_description.strip()), 120)
            merged = (
                f"{user_style}, {payload.style}"
                if payload.style.strip()
                else user_style
            )
            payload.style = (
                ensure_russian_vocal_style(merged) if not instrumental else merged
            )

        payload.style = enforce_style(
            payload.style,
            plan,
            reference=reference,
            backing_vocal=backing_vocal,
            backing_vocal_gender=backing_gender,
        )
        payload.style = compact_suno_style(payload.style)
        payload.title = sanitize_suno_title(payload.title, analyst_idea)
        payload.negative_tags = sanitize_negative_tags(
            payload.negative_tags, payload.style, plan.genre
        )
        payload.vocal_gender = plan.vocal_gender
        payload.style_weight = plan.style_weight
        payload.weirdness_constraint = plan.weirdness_constraint
        payload.audio_weight = plan.audio_weight

        if not package:
            if plan.instrumental:
                payload.lyrics = ""
            else:
                payload.lyrics = self.generate_lyrics(idea, plan)

        return plan, payload

    def _payload_from_unified_package(
        self,
        package,
        analysis: MusicAnalysis,
        *,
        backing_vocal: bool = False,
    ) -> SunoPromptPayload:
        genre_key = analysis.genre.lower().split()[0]
        style_weight = AiPromptComposer.STYLE_WEIGHT.get(
            genre_key, DEFAULT_STYLE_WEIGHT
        )
        weirdness = (
            DEFAULT_WEIRDNESS
            if analysis.commercial_intent == "commercial"
            else 0.50
        )
        negative_tags = self._composer._build_negative_tags(analysis.genre)
        negative_tags = AiPromptComposer._apply_vocal_negatives(
            negative_tags,
            analysis.vocal,
            backing_vocal,
        )

        vocal_gender = ""
        if analysis.vocal == "female":
            vocal_gender = "f"
        elif analysis.vocal == "male":
            vocal_gender = "m"

        return SunoPromptPayload(
            title=package.title,
            lyrics=package.lyrics,
            style=package.style,
            vocal_gender=vocal_gender,
            negative_tags=negative_tags,
            style_weight=style_weight,
            weirdness_constraint=weirdness,
            audio_weight=DEFAULT_AUDIO_WEIGHT,
        )

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
        for model_name, temperature, suffix in LYRICS_MODEL_ATTEMPTS:
            model = (
                self._yandex.MODEL_PRO
                if model_name == self._yandex.MODEL_PRO
                else self._yandex.MODEL_LITE
            )
            source = f"{model_name}" + (f"-{suffix}" if suffix else "")
            extra_hint = CLASSIC_LYRICS_RETRY_HINT if suffix else ""
            try:
                lyrics = clean_text(
                    self._yandex.complete(
                        CLASSIC_LYRICS_SYSTEM,
                        user_text + extra_hint,
                        max_tokens=3200,
                        temperature=temperature,
                        model=model,
                    )
                )
                lyrics = scrub_idea_echo_from_lyrics(lyrics, idea)
                lang_code, _, _ = resolve_lyrics_language(idea)
                wrong_lang = lang_code == "ru" and lyrics_look_english(lyrics)
                lazy = lyrics_look_lazy(lyrics, idea) if lyrics else True
                incomplete = (
                    lyrics_look_incomplete(lyrics, idea) if lyrics else True
                )
                if lyrics and not lazy and not incomplete and not wrong_lang:
                    return lyrics, source
                log.info(
                    "Lyrics attempt %s rejected (lazy=%s incomplete=%s wrong_lang=%s len=%s)",
                    source,
                    lazy,
                    incomplete,
                    wrong_lang,
                    len(lyrics) if lyrics else 0,
                )
            except Exception:
                log.exception("Lyrics attempt %s failed", source)

        log.warning("All lyrics attempts failed — using template fallback")
        return self._fallback_lyrics(idea), "template-fallback"

    @staticmethod
    def _lyrics_user_prompt(idea: str, plan: ProductionPlan) -> str:
        screenplay_hint = lyrics_screenplay_user_hint(
            genre=plan.genre,
            subgenre=plan.subgenre,
            mood=plan.mood,
            energy=plan.energy,
            idea=idea,
            backing_vocal=False,
        )
        return (
            f"БРИФ (не готовый текст — преврати в песню, не «что вижу — то пою»): {idea}\n"
            f"Жанр: {plan.genre} / {plan.subgenre}\n"
            f"Настроение: {plan.mood}\n"
            f"Энергия: {plan.energy}\n"
            f"BPM: {plan.bpm}\n"
            f"Вокал: {plan.vocal} — {plan.vocal_description}\n"
            f"Атмосфера: {plan.atmosphere}\n"
            f"Ориентир структуры: {plan.structure}\n"
            "ОБЯЗАТЕЛЬНО: полная песня ~4 минуты (lyrics 2000–4500 символов).\n"
            "Форма: Intro? → Verse1 → Pre → Chorus → Verse2 (новый ракурс) → Pre → "
            "Chorus → Bridge → Final Chorus → Outro. Припев дословно одинаков.\n"
            "Якоря (имена/места/детали) из брифа — вплетай естественно; "
            "не пересказывай бриф списком и не копируй фразы брифа в строки.\n"
            f"{screenplay_hint}\n"
            f"{lyrics_language_instruction(idea)}"
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
        # Запасной полноценный каркас ~4 мин, если YandexGPT недоступен.
        # Идея не вставляется дословно — только общий эмоциональный каркас.
        _ = (idea or "")[:80]
        return (
            "[Intro - soft pad, distant pulse]\n"
            "(мм…)\n\n"
            "[Verse 1 - intimate storytelling]\n"
            "Ночь ложится на плечи тихо\n"
            "Свет фонарей рисует путь\n"
            "Я храню в кармане слово\n"
            "Что не решался произнести\n"
            "Шаги по лужам отбивают ритм\n"
            "Город бережно держит меня\n"
            "В груди тепло и холод рядом\n"
            "И я иду навстречу дню\n\n"
            "[Pre-Chorus - building]\n"
            "Чуть громче сердце, чуть смелее взгляд\n"
            "Ещё один вдох — и я готов\n\n"
            "[Chorus - clear emotional hook]\n"
            "Держи меня в этом свете\n"
            "Пока не станет легче дышать\n"
            "Держи меня в этом свете\n"
            "Я научусь тебя слышать\n\n"
            "[Verse 2 - new angle]\n"
            "Утро стирает вчерашние тени\n"
            "На стекле чужие следы\n"
            "Я меняю старые привычки\n"
            "На честные простые «да»\n"
            "Пусть ветер сдувает сомнения\n"
            "Пусть карта ведёт не назад\n"
            "Я собираю себя по кускам\n"
            "И снова выбираю путь\n\n"
            "[Pre-Chorus - building]\n"
            "Чуть громче сердце, чуть смелее взгляд\n"
            "Ещё один вдох — и я готов\n\n"
            "[Chorus - clear emotional hook]\n"
            "Держи меня в этом свете\n"
            "Пока не станет легче дышать\n"
            "Держи меня в этом свете\n"
            "Я научусь тебя слышать\n\n"
            "[Bridge - strip-back then lift]\n"
            "Если тишина ответит первой\n"
            "Я не убегу — я останусь тут\n"
            "Между страхом и надеждой\n"
            "Выберу шаги вперёд\n\n"
            "[Final Chorus - full, layered vocals]\n"
            "Держи меня в этом свете\n"
            "Пока не станет легче дышать\n"
            "Держи меня в этом свете\n"
            "Я научусь тебя слышать\n"
            "(о-о-о)\n\n"
            "[Outro - fade]\n"
            "В этом свете…\n"
            "Я слышу."
        )