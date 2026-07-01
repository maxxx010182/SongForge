from backend.models import MusicAnalysis
from backend.services.genre_resolver import (
    SUBGENRE_BY_GENRE,
    infer_genre_from_idea,
    infer_mood_from_idea,
    resolve_genre,
    resolve_mood,
)
from backend.services.plan_overrides import apply_user_to_analysis
from backend.services.reference_translator import ReferenceTranslation
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
        "Если жанр или настроение не заданы пользователем — определи их по смыслу идеи, "
        "а не подставляй Pop по умолчанию. "
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
        reference: ReferenceTranslation | None = None,
        instrumental: bool = False,
        vocal_hint: str = "",
        backing_vocal: bool = False,
        style_mode: str = "presets",
        custom_description: str = "",
        locked_genre: bool = False,
        locked_artist: bool = False,
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
                if locked_genre:
                    hints.append(
                        "ОБЯЗАТЕЛЬНО: пользователь явно указал жанр в идее. "
                        "Не меняй жанр на Pop/Ballad даже при романтической теме."
                    )
            if mood.strip():
                hints.append(f"Настроение от пользователя: {mood.strip()}")
            if not genre.strip() and not mood.strip():
                hints.append(
                    "Жанр и настроение не заданы — определи их по смыслу идеи, "
                    "не используй Pop по умолчанию без оснований."
                )

        if reference and reference.has_content:
            hints.append(
                f"Референс звучания (без имён артистов в ответе): {reference.style_tags}"
            )
            if locked_artist:
                hints.append(
                    "ОБЯЗАТЕЛЬНО: пользователь указал референс артиста в идее. "
                    "Сохрани характер звучания референса в жанре, вокале и продакшне."
                )
            if reference.genre:
                hints.append(
                    f"Жанр по референсу: {reference.genre} / {reference.subgenre}"
                )
            if reference.vocal_description:
                hints.append(f"Вокал по референсу: {reference.vocal_description}")
            if reference.bpm:
                hints.append(f"Ориентир BPM по референсу: {reference.bpm}")
            if not genre.strip():
                hints.append(
                    "Если жанр пользователем не задан — опирайся на жанр референса."
                )
        if vocal_hint == "duet":
            hints.append(
                "ОБЯЗАТЕЛЬНО дуэт: мужской И женский вокал в одном треке, "
                "чередование или совместное пение."
            )
        elif not custom_mode and vocal_hint.strip() and vocal_hint != "auto":
            hints.append(f"Пожелание по вокалу: {vocal_hint.strip()}")
        if backing_vocal:
            hints.append(
                "ОБЯЗАТЕЛЬНЫ бэк-вокалы и гармонии на припевах, бридже и аутро."
            )
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
            analysis = self._normalize(analysis)
            analysis = apply_user_to_analysis(
                analysis,
                genre=genre,
                mood=mood,
                vocal_hint=vocal_hint,
            )
            if reference and reference.has_content and not genre.strip():
                if reference.genre:
                    analysis.genre = reference.genre
                if reference.subgenre:
                    analysis.subgenre = reference.subgenre
                if reference.bpm:
                    analysis.bpm = reference.bpm
                if reference.vocal_description and vocal_hint == "auto":
                    analysis.vocal_description = reference.vocal_description
            return analysis
        except Exception:
            return self._fallback(
                idea,
                genre=genre,
                mood=mood,
                instrumental=instrumental,
                vocal_hint=vocal_hint,
                reference=reference,
            )

    _resolve_genre = staticmethod(resolve_genre)
    _resolve_mood = staticmethod(resolve_mood)
    _infer_genre_from_idea = staticmethod(infer_genre_from_idea)
    _infer_mood_from_idea = staticmethod(infer_mood_from_idea)

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

    @classmethod
    def _fallback(
        cls,
        idea: str,
        *,
        genre: str = "",
        mood: str = "",
        instrumental: bool = False,
        vocal_hint: str = "",
        reference: ReferenceTranslation | None = None,
    ) -> MusicAnalysis:
        vocal = vocal_hint if vocal_hint in {"male", "female", "duet", "auto"} else "auto"
        if reference and reference.has_content and not genre.strip():
            genre_en = reference.genre or cls._resolve_genre(genre, idea)[0]
            subgenre = reference.subgenre or SUBGENRE_BY_GENRE.get(genre_en, "Modern")
            vocal_description = reference.vocal_description or "expressive modern vocals"
            bpm = reference.bpm or 120
        else:
            genre_en, subgenre = cls._resolve_genre(genre, idea)
            vocal_description = "expressive modern vocals"
            bpm = 120
        mood_en = cls._resolve_mood(mood, idea)
        analysis = MusicAnalysis(
            genre=genre_en,
            subgenre=subgenre,
            mood=mood_en,
            bpm=bpm,
            energy="medium",
            instruments=["synth", "drums", "bass", "electric guitar"],
            atmosphere="modern emotional atmosphere",
            vocal=vocal,
            vocal_description=vocal_description,
            production_style="radio-ready polished mix",
            commercial_intent="commercial",
            structure="verse-chorus-verse-chorus-bridge-chorus-outro",
            instrumental=instrumental,
            idea=idea,
        )
        return apply_user_to_analysis(
            analysis,
            genre=genre,
            mood=mood,
            vocal_hint=vocal_hint,
        )