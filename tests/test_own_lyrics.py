"""Свой текст в расширенном режиме поётся как есть. Описание остаётся в стиле."""

from backend.services.prompt_builder import PromptBuilder
from backend.services.provided_song import keep_own_lyrics

_OWN = """Куплет 1
Шур юр, урам тулли
Припев
Тинёс таврашёсем
"""

_WISH = "чувашская песня о родной земле, близких и единстве народа"

_ANALYST = (
    '{"genre":"Folk","subgenre":"Chuvash Folk","mood":"warm",'
    '"bpm":96,"energy":"medium","instruments":["Accordion","Acoustic Guitar"],'
    '"atmosphere":"homeland","vocal":"male",'
    '"vocal_description":"warm choir-like vocal",'
    '"production_style":"folk acoustic",'
    '"commercial_intent":"commercial",'
    '"structure":"verse-chorus"}'
)


def test_short_own_lyrics_keep_lines_and_english_labels():
    lyrics = keep_own_lyrics(_OWN)
    assert "[Verse 1]" in lyrics
    assert "[Chorus]" in lyrics
    assert "Шур юр, урам тулли" in lyrics
    assert "Тинёс" in lyrics


def test_own_lyrics_are_not_rewritten_and_wish_reaches_the_model():
    class See:
        MODEL_PRO = "yandexgpt"
        MODEL_LITE = "yandexgpt-lite"

        def __init__(self):
            self.users: list[str] = []
            self.systems: list[str] = []

        def complete(self, system, user, **kwargs):
            self.systems.append(system)
            self.users.append(user)
            return _ANALYST

    fake = See()
    plan, payload = PromptBuilder(fake).build(
        _WISH,
        genre="Поп",
        mood="uplifting",
        lyrics_engine="unified",
        own_lyrics=_OWN,
    )
    assert len(fake.systems) == 1
    assert "Analyst" in fake.systems[0]
    assert "Шур юр" not in fake.users[0]
    assert "чувашская" in fake.users[0]
    assert "Шур юр, урам тулли" in payload.lyrics
    assert "чувашская песня о родной земле" in payload.style.lower()
    assert plan.genre == "Pop"


def test_wish_stays_in_style_when_the_model_is_silent():
    class Down:
        MODEL_PRO = "yandexgpt"
        MODEL_LITE = "yandexgpt-lite"

        def complete(self, *args, **kwargs):
            raise RuntimeError("kie down")

    _plan, payload = PromptBuilder(Down()).build(
        _WISH,
        genre="",
        mood="",
        lyrics_engine="unified",
        own_lyrics=_OWN,
    )
    assert "Шур юр, урам тулли" in payload.lyrics
    assert "[Chorus]" in payload.lyrics
    assert "чувашская песня о родной земле" in payload.style.lower()
    assert payload.title
