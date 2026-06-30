from backend.models import MusicAnalysis, SunoPromptPayload
from backend.services.artist_reference import resolve_artist_reference
from backend.services.yandex_client import YandexClient
from backend.settings import DEFAULT_AUDIO_WEIGHT, DEFAULT_STYLE_WEIGHT, DEFAULT_WEIRDNESS
from backend.utils.text import clean_text, ensure_russian_vocal_style, extract_json, truncate


class AiPromptComposer:
    SYSTEM_VOCAL = (
        "Ты AI Prompt Composer для SongForge и Suno V5.5. "
        "На основе музыкального анализа создай профессиональные параметры генерации. "
        "Верни ТОЛЬКО валидный JSON без markdown и обычного текста. "
        "Поля: "
        "title (короткое запоминающееся название на русском, до 4 слов), "
        "lyrics (полный текст песни на русском со структурными тегами "
        "[Verse 1], [Chorus], [Verse 2], [Chorus], [Bridge], [Chorus], [Outro]), "
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
        "negativeTags, styleWeight (0.50), weirdnessConstraint (0.30), audioWeight (0.50). "
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
        "pop": 0.50,
        "rock": 0.50,
        "electronic": 0.55,
        "epic": 0.55,
        "lo-fi": 0.45,
    }

    def __init__(self, yandex: YandexClient) -> None:
        self._yandex = yandex

    def compose(
        self,
        analysis: MusicAnalysis,
        idea: str,
        *,
        artist_ref: str = "",
        vocal_hint: str = "",
        backing_vocal: bool = False,
    ) -> SunoPromptPayload:
        system = (
            self.SYSTEM_INSTRUMENTAL if analysis.instrumental else self.SYSTEM_VOCAL
        )
        user_text = self._build_user_prompt(
            analysis,
            idea,
            artist_ref=artist_ref,
            vocal_hint=vocal_hint,
            backing_vocal=backing_vocal,
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
                artist_ref=artist_ref,
                backing_vocal=backing_vocal,
            )
        except Exception:
            return self._fallback(
                analysis,
                idea,
                artist_ref=artist_ref,
                backing_vocal=backing_vocal,
            )

    @staticmethod
    def _build_user_prompt(
        analysis: MusicAnalysis,
        idea: str,
        *,
        artist_ref: str = "",
        vocal_hint: str = "",
        backing_vocal: bool = False,
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
        artist_profile = resolve_artist_reference(artist_ref)
        if artist_profile:
            parts.append(f"Artist reference style (no names): {artist_profile.style_tags}")
        elif artist_ref.strip():
            parts.append(f"Artist reference (no names): {artist_ref.strip()}")
        if vocal_hint == "duet" or analysis.vocal == "duet":
            parts.append(
                "MANDATORY duet: male AND female lead vocals in the same track."
            )
        if backing_vocal:
            parts.append(
                "MANDATORY layered backing vocals, vocal harmonies, chorus stacks."
            )
        if analysis.instrumental:
            parts.append("Instrumental only — no vocals, lyrics must be empty.")
        return "\n".join(parts)

    def _normalize(
        self,
        payload: SunoPromptPayload,
        analysis: MusicAnalysis,
        *,
        artist_ref: str = "",
        backing_vocal: bool = False,
    ) -> SunoPromptPayload:
        payload.title = truncate(clean_text(payload.title).strip("\"'«»"), 75)
        payload.style = truncate(clean_text(payload.style), 950)

        if analysis.instrumental:
            payload.lyrics = ""
            payload.vocal_gender = ""
        else:
            payload.lyrics = clean_text(payload.lyrics)
            payload.style = truncate(ensure_russian_vocal_style(payload.style), 950)

        artist_profile = resolve_artist_reference(artist_ref)
        if artist_profile and artist_profile.style_tags.lower() not in payload.style.lower():
            payload.style = f"{artist_profile.style_tags}, {payload.style}"

        payload.style = self._apply_vocal_style(payload.style, analysis.vocal, backing_vocal)
        payload.style = truncate(payload.style, 950)

        payload.style_weight = max(0.0, min(float(payload.style_weight), 1.0))
        payload.weirdness_constraint = max(
            0.0, min(float(payload.weirdness_constraint), 1.0)
        )
        payload.audio_weight = max(0.0, min(float(payload.audio_weight), 1.0))

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
        artist_ref: str = "",
        backing_vocal: bool = False,
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
        artist_profile = resolve_artist_reference(artist_ref)
        if artist_profile:
            style_parts.insert(0, artist_profile.style_tags)

        style = ", ".join(p for p in style_parts if p)
        if not analysis.instrumental:
            style = ensure_russian_vocal_style(style)
            style = self._apply_vocal_style(style, analysis.vocal, backing_vocal)
            style = truncate(style, 950)
        genre_key = analysis.genre.lower().split()[0]
        style_weight = self.STYLE_WEIGHT.get(genre_key, DEFAULT_STYLE_WEIGHT)
        weirdness = DEFAULT_WEIRDNESS if analysis.commercial_intent == "commercial" else 0.50
        audio_weight = DEFAULT_AUDIO_WEIGHT

        words = [w for w in idea.split() if w.strip()]
        title = truncate(" ".join(words[:4]) if words else "Моя песня", 75)

        lyrics = ""
        if not analysis.instrumental:
            snippet = truncate(idea, 60)
            lyrics = (
                f"[Verse 1]\n{snippet}\nМузыка ведёт меня вперёд\n\n"
                f"[Chorus]\nЭто моя песня, мой огонь\n"
                f"Звучит внутри и снаружи\n\n"
                f"[Verse 2]\nКаждый бит — как новый день\n\n"
                f"[Chorus]\nЭто моя песня, мой огонь\n\n"
                f"[Outro]\nНавсегда."
            )

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