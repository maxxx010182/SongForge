from backend.models import MusicAnalysis, SunoPromptPayload
from backend.services.reference_translator import ReferenceTranslation
from backend.services.style_enforcer import enforce_style
from backend.services.llm_factory import LlmClient
from backend.settings import DEFAULT_AUDIO_WEIGHT, DEFAULT_STYLE_WEIGHT, DEFAULT_WEIRDNESS
from backend.utils.text import clean_text, ensure_russian_vocal_style, extract_json, truncate


class AiPromptComposer:
    SYSTEM_VOCAL = (
        "Ты AI Prompt Composer для SongForge и Suno V5.5. "
        "На основе музыкального анализа создай профессиональные параметры генерации. "
        "Верни ТОЛЬКО валидный JSON без markdown и обычного текста. "
        "Поля: "
        "title (короткое название песни на русском, до 4 слов; "
        "НЕ сценические ремарки вроде [Crowd noise] или [Intro]), "
        "lyrics (всегда пустая строка \"\" — текст песни генерируется отдельно), "
        "style (подробное описание на английском в одну строку через запятую: "
        "жанр, поджанр, настроение, BPM, энергия, инструменты, вокал, атмосфера, сведение; "
        "обязательно включи: sung in Russian, native Russian vocals), "
        "vocalGender (пустая строка \"\" для duet; f или m только для соло), "
        "negativeTags (список исключений через запятую на английском), "
        "styleWeight (0.0-1.0), weirdnessConstraint (0.0-1.0), audioWeight (0.0-1.0). "
        "Запрещено: общие описания, короткий style, дублирование жанров, бессмысленные слова. "
        "negativeTags обязательно включает: unwanted noise, distortion, clipping, screaming, "
        "off-key vocals, poor mix, muddy sound, low quality, chaotic arrangement "
        "и дополняется по жанру."
    )

    SYSTEM_INSTRUMENTAL = (
        "Ты AI Prompt Composer для SongForge и Suno V5.5. "
        "Создай параметры для ИНСТРУМЕНТАЛЬНОГО трека без вокала. "
        "Верни ТОЛЬКО валидный JSON без markdown. "
        "Поля: "
        "title (короткое название на русском), "
        "lyrics (пустая строка \"\"), "
        "style (максимально подробное музыкальное описание на английском: жанр, поджанр, "
        "настроение, BPM, энергия, инструменты, атмосфера, сведение, коммерческое звучание), "
        "vocalGender (пустая строка \"\"), "
        "negativeTags, styleWeight (0.85), weirdnessConstraint (0.20), audioWeight (0.70). "
        "Не создавай текст песни. lyrics всегда \"\"."
    )

    BASE_NEGATIVE = (
        "unwanted noise, distortion, clipping, screaming, off-key vocals, "
        "poor mix, muddy sound, low quality, chaotic arrangement"
    )

    GENRE_NEGATIVE: dict[str, str] = {
        "pop": "heavy metal, scream, aggressive distortion",
        "rock": "synth pop cliché, weak drums, thin guitars",
        "hip-hop": "country twang, opera vocals, weak 808",
        "electronic": "acoustic only, lo-fi hiss, weak bass",
        "lo-fi": "harsh compression, bright EDM drops, aggressive vocals",
        "metal": "soft pop vocals, weak guitars, thin mix",
        "ballad": "aggressive rap, heavy distortion, chaotic drums",
    }

    STYLE_WEIGHT: dict[str, float] = {
        "pop": 0.85,
        "rock": 0.80,
        "electronic": 0.85,
        "epic": 0.90,
        "lo-fi": 0.75,
    }

    def __init__(self, yandex: LlmClient) -> None:
        self._yandex = yandex

    def compose(
        self,
        analysis: MusicAnalysis,
        idea: str,
        *,
        reference: ReferenceTranslation | None = None,
        vocal_hint: str = "",
        backing_vocal: bool = False,
        backing_vocal_gender: str = "",
    ) -> SunoPromptPayload:
        system = (
            self.SYSTEM_INSTRUMENTAL if analysis.instrumental else self.SYSTEM_VOCAL
        )
        user_text = self._build_user_prompt(
            analysis,
            idea,
            reference=reference,
            vocal_hint=vocal_hint,
            backing_vocal=backing_vocal,
            backing_vocal_gender=backing_vocal_gender,
        )

        try:
            raw = self._yandex.complete(
                system,
                user_text,
                max_tokens=1200,
                temperature=0.55,
            )
            data = extract_json(raw)
            payload = SunoPromptPayload.model_validate(data)
            return self._normalize(
                payload,
                analysis,
                reference=reference,
                backing_vocal=backing_vocal,
                backing_vocal_gender=backing_vocal_gender,
            )
        except Exception:
            return self._fallback(
                analysis,
                idea,
                reference=reference,
                backing_vocal=backing_vocal,
                backing_vocal_gender=backing_vocal_gender,
            )

    @staticmethod
    def _build_user_prompt(
        analysis: MusicAnalysis,
        idea: str,
        *,
        reference: ReferenceTranslation | None = None,
        vocal_hint: str = "",
        backing_vocal: bool = False,
        backing_vocal_gender: str = "",
    ) -> str:
        parts = [
            f"Идея: {idea}",
            f"Genre: {analysis.genre}",
            f"Subgenre: {analysis.subgenre}",
            f"Mood: {analysis.mood}",
            f"BPM: {analysis.bpm}",
            f"Energy: {analysis.energy}",
            f"Instruments: {', '.join(analysis.instruments)}",
            f"Atmosphere: {analysis.atmosphere}",
            f"Vocal: {analysis.vocal} — {analysis.vocal_description}",
            f"Production: {analysis.production_style}",
            f"Commercial intent: {analysis.commercial_intent}",
            f"Structure: {analysis.structure}",
        ]
        if reference and reference.has_content:
            parts.append(f"Artist reference style (no names): {reference.style_tags}")
            if reference.vocal_description:
                parts.append(f"Reference vocal character: {reference.vocal_description}")
        if vocal_hint == "duet" or analysis.vocal == "duet":
            parts.append(
                "MANDATORY duet: male AND female lead vocals in the same track."
            )
        if backing_vocal:
            backing_line = (
                "MANDATORY layered backing vocals, vocal harmonies, chorus stacks."
            )
            if backing_vocal_gender == "f":
                backing_line = (
                    "MANDATORY female backing vocals on chorus, "
                    "layered female harmonies, female chorus stacks."
                )
            parts.append(backing_line)
        if analysis.instrumental:
            parts.append("Instrumental only — no vocals, lyrics must be empty.")
        return "\n".join(parts)

    def _normalize(
        self,
        payload: SunoPromptPayload,
        analysis: MusicAnalysis,
        *,
        reference: ReferenceTranslation | None = None,
        backing_vocal: bool = False,
    ) -> SunoPromptPayload:
        payload.title = truncate(clean_text(payload.title).strip("\"'«»"), 75)
        payload.style = truncate(clean_text(payload.style), 950)

        if analysis.instrumental:
            payload.lyrics = ""
            payload.vocal_gender = ""
        else:
            payload.lyrics = ""
            payload.style = truncate(ensure_russian_vocal_style(payload.style), 950)

        payload.style_weight = max(0.0, min(float(payload.style_weight), 1.0))
        payload.weirdness_constraint = max(
            0.0, min(float(payload.weirdness_constraint), 1.0)
        )
        payload.audio_weight = max(0.0, min(float(payload.audio_weight), 1.0))

        if payload.style_weight <= 0.55:
            genre_key = analysis.genre.lower().split()[0]
            payload.style_weight = self.STYLE_WEIGHT.get(
                genre_key, DEFAULT_STYLE_WEIGHT
            )
        if payload.weirdness_constraint <= 0.0:
            payload.weirdness_constraint = (
                DEFAULT_WEIRDNESS
                if analysis.commercial_intent == "commercial"
                else 0.50
            )
        if payload.audio_weight <= 0.55:
            payload.audio_weight = DEFAULT_AUDIO_WEIGHT

        if not payload.negative_tags.strip():
            payload.negative_tags = self._build_negative_tags(analysis.genre)
        payload.negative_tags = self._apply_vocal_negatives(
            payload.negative_tags,
            analysis.vocal,
            backing_vocal,
        )

        if analysis.vocal == "duet":
            payload.vocal_gender = ""
        else:
            gender = (payload.vocal_gender or "").strip().lower()
            if gender in {"f", "female", "ж", "женский"}:
                payload.vocal_gender = "f"
            elif gender in {"m", "male", "м", "мужской"}:
                payload.vocal_gender = "m"
            elif analysis.vocal == "female":
                payload.vocal_gender = "f"
            elif analysis.vocal == "male":
                payload.vocal_gender = "m"
            else:
                payload.vocal_gender = gender if gender in {"f", "m"} else ""

        return payload

    @staticmethod
    def _analysis_as_plan(analysis: MusicAnalysis, payload: SunoPromptPayload):
        from backend.models import ProductionPlan

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
            negative_tags=payload.negative_tags,
            style_weight=payload.style_weight,
            weirdness_constraint=payload.weirdness_constraint,
            audio_weight=payload.audio_weight,
            vocal_gender=payload.vocal_gender,
            instrumental=analysis.instrumental,
        )

    @staticmethod
    def _apply_vocal_style(style: str, vocal: str, backing_vocal: bool) -> str:
        lower = style.lower()
        if vocal == "duet" and "duet" not in lower:
            style += (
                ", male and female duet vocals, dual lead vocals, "
                "alternating male and female verses, male rap with female hook"
            )
        if backing_vocal and "backing vocal" not in lower:
            style += (
                ", layered backing vocals, rich vocal harmonies, "
                "chorus vocal stacks, call-and-response backing vocals"
            )
        return style

    @staticmethod
    def _apply_vocal_negatives(negative_tags: str, vocal: str, backing_vocal: bool) -> str:
        extras: list[str] = []
        if vocal == "duet":
            extras.append("solo female only, solo male only, single vocalist, one voice only")
        if backing_vocal:
            extras.append("a cappella, dry solo vocal, no backing vocals, no harmonies")
        if not extras:
            return negative_tags
        suffix = ", ".join(extras)
        if suffix.lower() in negative_tags.lower():
            return negative_tags
        return f"{negative_tags}, {suffix}" if negative_tags.strip() else suffix

    def _fallback(
        self,
        analysis: MusicAnalysis,
        idea: str,
        *,
        reference: ReferenceTranslation | None = None,
        backing_vocal: bool = False,
        backing_vocal_gender: str = "",
    ) -> SunoPromptPayload:
        instruments = ", ".join(analysis.instruments)
        style_parts = [
            f"Modern commercial {analysis.genre.lower()}",
            analysis.subgenre,
            f"{analysis.mood} mood",
            f"{analysis.bpm} BPM",
            f"{analysis.energy} energy",
            instruments,
            analysis.vocal_description,
            analysis.production_style,
            analysis.atmosphere,
            "wide stereo",
            "radio-ready production",
            "memorable chorus",
            "high quality mix",
        ]
        plan_snapshot = self._analysis_as_plan(
            analysis,
            SunoPromptPayload(negative_tags=self._build_negative_tags(analysis.genre)),
        )
        style = enforce_style(
            ", ".join(p for p in style_parts if p),
            plan_snapshot,
            reference=reference,
            backing_vocal=backing_vocal,
            backing_vocal_gender=backing_vocal_gender,
        )
        genre_key = analysis.genre.lower().split()[0]
        style_weight = self.STYLE_WEIGHT.get(genre_key, DEFAULT_STYLE_WEIGHT)
        weirdness = DEFAULT_WEIRDNESS if analysis.commercial_intent == "commercial" else 0.50
        audio_weight = DEFAULT_AUDIO_WEIGHT

        words = [w for w in idea.split() if w.strip()]
        title = truncate(" ".join(words[:4]) if words else "Моя песня", 75)

        lyrics = ""

        vocal_gender = ""
        if analysis.vocal == "female":
            vocal_gender = "f"
        elif analysis.vocal == "male":
            vocal_gender = "m"

        negative_tags = self._build_negative_tags(analysis.genre)
        negative_tags = self._apply_vocal_negatives(
            negative_tags,
            analysis.vocal,
            backing_vocal,
        )

        return SunoPromptPayload(
            title=title,
            lyrics=lyrics,
            style=truncate(style, 950),
            vocal_gender=vocal_gender,
            negative_tags=negative_tags,
            style_weight=style_weight,
            weirdness_constraint=weirdness,
            audio_weight=audio_weight,
        )

    def _build_negative_tags(self, genre: str) -> str:
        key = genre.lower().split()[0]
        extra = self.GENRE_NEGATIVE.get(key, "amateur recording, weak arrangement")
        return f"{self.BASE_NEGATIVE}, {extra}"