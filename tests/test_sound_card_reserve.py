"""Карточка звучания: ошибка первой модели не останавливает песню."""

import json

from backend.services.ai_music_analyst import AiMusicAnalyst
from backend.services.prompt_builder import PromptBuilder
from tests.test_suno_package_composer import _full_lyrics


_IDEA = "Создай трек в жанре Поп, энергичный и современный"


class _Card:
    MODEL_PRO = "yandexgpt"
    MODEL_LITE = "yandexgpt-lite"

    def __init__(self) -> None:
        self.reserve: list[bool] = []
        self.systems: list[str] = []

    def complete(self, system, user, **kwargs):
        self.systems.append(system)
        self.reserve.append(bool(kwargs.get("reserve")))
        if "Analyst" in system:
            raise RuntimeError("Internal Error, Please try again later. code 500")
        return json.dumps(
            {
                "title": "Вечеринка",
                "lyrics": _full_lyrics(),
                "style_prompt": "pop, party, female vocals, 120 bpm",
            },
            ensure_ascii=False,
        )


def test_sound_card_asks_with_reserve():
    seen = {}

    class Once:
        MODEL_PRO = "yandexgpt"
        MODEL_LITE = "yandexgpt-lite"

        def complete(self, system, user, **kwargs):
            seen["reserve"] = kwargs.get("reserve")
            return json.dumps(
                {
                    "genre": "Pop",
                    "subgenre": "Modern Pop",
                    "mood": "party",
                    "bpm": 118,
                    "energy": "high",
                    "instruments": ["synth", "drums", "bass", "piano"],
                    "atmosphere": "bright",
                    "vocal": "female",
                    "vocal_description": "bright female lead",
                    "production_style": "radio mix",
                    "commercial_intent": "commercial",
                    "structure": "verse-chorus",
                }
            )

    analysis = AiMusicAnalyst(Once()).analyze(
        _IDEA,
        genre="Поп",
        mood="party",
        vocal_hint="female",
    )
    assert seen["reserve"] is True
    assert analysis.genre == "Pop"
    assert analysis.vocal == "female"


def test_failed_sound_card_still_asks_for_lyrics():
    card = _Card()
    plan, payload = PromptBuilder(card).build(
        _IDEA,
        genre="Поп",
        mood="party",
        vocal_hint="female",
        lyrics_engine="unified",
    )
    assert card.reserve[0] is True
    assert any("Analyst" not in system for system in card.systems)
    assert plan.genre == "Pop"
    assert plan.mood == "party"
    assert plan.vocal == "female"
    assert plan.bpm == 120
    assert "Тюмень" in payload.lyrics
