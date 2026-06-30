from backend.models import MusicAnalysis
from backend.services.yandex_client import YandexClient
from backend.utils.text import extract_json


class AiMusicAnalyst:
    SYSTEM = (
        "Ты AI Music Analyst для SongForge — интеллектуального слоя перед Suno V5.5. "
        "Проанализируй идею пользователя и верни ТОЛЬКО валидный JSON без markdown и текста. "
        "Поля: "
        "genre (основной жанр на английском), "
        "subgenre (поджанр на английском), "
        "mood (настроение на английском), "
        "bpm (число 60-200), "
        "energy (low|medium|high), "
        "instruments (массив 4-8 инструментов на английском), "
        "atmosphere (атмосфера на английском), "
        "vocal (male|female|duet|auto), "
        "vocal_description (описание вокала на английском), "
        "production_style (тип сведения на английском), "
        "commercial_intent (commercial|experimental), "
        "structure (структура трека, например verse-chorus-verse-chorus-bridge-chorus). "
        "Не упоминай имена артистов. Будь конкретным и профессиональным."
    )

    def __init__(self, yandex: YandexClient) -> None:
        self._yandex = yandex

    def analyze(
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
    ) -> MusicAnalysis:
        hints: list[str] = []
        custom_mode = style_mode == "custom" and custom_description.strip()

        if custom_mode:
            user_text = f"Описание желаемого звучания своими словами:\n{custom_description.strip()}"
            if idea.strip():
                user_text = (
                    f"Идея песни: {idea.strip()}\n\n{user_text}"
                )
            hints.append(
                "Режим «своими словами»: извлеки жанр, поджанр, настроение, "
                "вокал, BPM, энергию и инструменты из описания пользователя. "
                "Списки жанра и настроения не заданы — опирайся только на текст."
            )
        else:
            user_text = idea.strip()
            if genre.strip():
                hints.append(f"Жанр от пользователя: {genre.strip()}")
            if mood.strip():
                hints.append(f"Настроение от пользователя: {mood.strip()}")

        if artist_ref.strip():
            hints.append(
                f"Референс звучания (без имён в треке): {artist_ref.strip()}"
            )
        if not custom_mode and vocal_hint.strip() and vocal_hint != "auto":
            hints.append(f"Пожелание по вокалу: {vocal_hint.strip()}")
        if backing_vocal:
            hints.append("Нужны бэк-вокалы и гармонии.")
        if instrumental:
            hints.append(
                "Инструментальный трек без вокала — анализируй только музыкальную концепцию."
            )

        if hints:
            user_text += "\n\n" + "\n".join(hints)

        try:
            raw = self._yandex.complete(
                self.SYSTEM,
                user_text,
                max_tokens=700,
                temperature=0.45,
            )
            data = extract_json(raw)
            analysis = MusicAnalysis.model_validate(data)
            analysis.instrumental = instrumental
            if vocal_hint in {"male", "female", "duet", "auto"}:
                analysis.vocal = vocal_hint
            return self._normalize(analysis)
        except Exception:
            return self._fallback(
                idea,
                genre=genre,
                mood=mood,
                instrumental=instrumental,
                vocal_hint=vocal_hint,
            )

    @staticmethod
    def _normalize(analysis: MusicAnalysis) -> MusicAnalysis:
        analysis.bpm = max(60, min(int(analysis.bpm or 120), 200))
        if analysis.vocal not in {"male", "female", "duet", "auto"}:
            analysis.vocal = "auto"
        if not analysis.instruments:
            analysis.instruments = ["piano", "synth pads", "drums", "bass"]
        if analysis.commercial_intent not in {"commercial", "experimental"}:
            analysis.commercial_intent = "commercial"
        return analysis

    @staticmethod
    def _fallback(
        idea: str,
        *,
        genre: str = "",
        mood: str = "",
        instrumental: bool = False,
        vocal_hint: str = "",
    ) -> MusicAnalysis:
        vocal = vocal_hint if vocal_hint in {"male", "female", "duet", "auto"} else "auto"
        genre_en = genre or "Pop"
        mood_en = mood or "uplifting"
        return MusicAnalysis(
            genre=genre_en,
            subgenre="Modern Pop",
            mood=mood_en,
            bpm=120,
            energy="medium",
            instruments=["synth", "drums", "bass", "electric guitar"],
            atmosphere="modern emotional atmosphere",
            vocal=vocal,
            vocal_description="expressive modern vocals",
            production_style="radio-ready polished mix",
            commercial_intent="commercial",
            structure="verse-chorus-verse-chorus-bridge-chorus-outro",
            instrumental=instrumental,
            idea=idea,
        )