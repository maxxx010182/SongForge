from dataclasses import dataclass

from backend.services.yandex_client import YandexClient
from backend.utils.text import clean_text, extract_json, truncate


@dataclass
class ReferenceTranslation:
    """Sonic fingerprint of an artist reference — no names, safe for Suno."""

    source: str
    genre: str = ""
    subgenre: str = ""
    style_tags: str = ""
    vocal_description: str = ""
    bpm: int = 0

    @property
    def has_content(self) -> bool:
        return bool(
            self.style_tags.strip()
            or self.genre.strip()
            or self.vocal_description.strip()
        )


class ReferenceTranslator:
    SYSTEM = (
        "Ты музыкальный продюсер и эксперт по Suno V5.5. "
        "Пользователь указывает референс — исполнителя или группу. "
        "Твоя задача: описать ЗВУЧАНИЕ этого референса для генерации похожей музыки. "
        "Верни ТОЛЬКО валидный JSON без markdown. Поля: "
        "genre (основной жанр на английском), "
        "subgenre (поджанр на английском), "
        "style_tags (одна строка на английском через запятую: жанр, инструменты, "
        "характер вокала, продакшн, эпоха, атмосфера, темп — 8-15 конкретных тегов), "
        "vocal_description (характер вокала на английском), "
        "bpm (число 60-200 или 0 если неясно). "
        "ЗАПРЕЩЕНО: имена артистов, названия групп, названия песен, альбомов, "
        "любые proper nouns исполнителей. Только описание звука и продакшна."
    )

    def __init__(self, yandex: YandexClient) -> None:
        self._yandex = yandex

    def translate(self, artist_ref: str, *, idea: str = "") -> ReferenceTranslation:
        ref = artist_ref.strip()
        if not ref:
            return ReferenceTranslation(source="")

        user_text = f"Референс исполнителя или группы: {ref}"
        if idea.strip():
            user_text += f"\nКонтекст идеи песни: {idea.strip()}"

        try:
            raw = self._yandex.complete(
                self.SYSTEM,
                user_text,
                max_tokens=400,
                temperature=0.35,
            )
            data = extract_json(raw)
            return ReferenceTranslation(
                source=ref,
                genre=clean_text(str(data.get("genre", ""))),
                subgenre=clean_text(str(data.get("subgenre", ""))),
                style_tags=truncate(clean_text(str(data.get("style_tags", ""))), 500),
                vocal_description=clean_text(str(data.get("vocal_description", ""))),
                bpm=max(0, min(int(data.get("bpm") or 0), 200)),
            )
        except Exception:
            return ReferenceTranslation(
                source=ref,
                style_tags=truncate(
                    "distinctive commercial production, recognizable vocal character, "
                    "genre-appropriate instrumentation, polished radio-ready mix, "
                    "emotional delivery, modern studio sound",
                    500,
                ),
            )