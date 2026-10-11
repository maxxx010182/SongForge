"""Готовая песня в идее поётся как есть. Короткая просьба по-прежнему пишется."""

from backend.models import ProductionPlan
from backend.services.idea_parser import parse_idea
from backend.services.prompt_builder import PromptBuilder
from backend.services.provided_song import extract_provided_song
from backend.utils.text import scrub_idea_echo_from_lyrics

_PASTED = """
Теперь песня стала по-настоящему полной.

**Жанр:** ироничный поп-рок.
**Настроение:** очень теплое.

**Текст песни:**

*(Куплет 1)*
У дяди дома тихо и тепло
На люстре носки и старый диплом
В холодильнике только лёд
Он пельмени с ножа бросает в рот

*(Припев)*
Но стоит в прихожей раздаться звонку
И ключ провернуться в замке наверху
Летят две торпеды сметая углы
Наш дорогой человек уже тут

*(Куплет 2)*
Включает им Форсаж вместо Спокойной ночи
И красит ему волосы духами
А рыжая кошка ведет весь дом
И в миске у неё лосось а не корм

**Совет для генерации музыки:** сделай поп-рок.
"""

_ANALYST = (
    '{"genre":"Pop-Rock","subgenre":"Ironic Pop-Rock","mood":"warm",'
    '"bpm":110,"energy":"medium","instruments":["Acoustic Guitar","Bass"],'
    '"atmosphere":"cozy","vocal":"male",'
    '"vocal_description":"warm male vocal",'
    '"production_style":"clean pop-rock",'
    '"commercial_intent":"commercial",'
    '"structure":"verse-chorus-verse-chorus"}'
)


class _FakeLlm:
    MODEL_PRO = "yandexgpt"
    MODEL_LITE = "yandexgpt-lite"

    def __init__(self):
        self.systems: list[str] = []

    def complete(self, system, user, **kwargs):
        self.systems.append(system)
        if "сонграйтер" in system.lower() or "lyrics" in system.lower():
            raise AssertionError("готовую песню нельзя переписывать")
        return _ANALYST


def test_pasted_song_keeps_verses_and_drops_chat_wrapper():
    lyrics = extract_provided_song(_PASTED)
    assert "[Verse 1]" in lyrics
    assert "[Chorus]" in lyrics
    assert "У дяди дома тихо и тепло" in lyrics
    assert "Спокойной ночи" in lyrics
    assert "Теперь песня стала" not in lyrics
    assert "Совет для генерации" not in lyrics
    assert "ироничный поп-рок" not in lyrics


def test_short_wish_and_a_mention_of_a_verse_are_not_a_song():
    assert extract_provided_song("песня маме про сад") == ""
    assert extract_provided_song("немного репа в куплете, но в целом спокойно") == ""
    story = "Он жил в гараже. Потом приехала родня. Кошка спала на кресле. " * 8
    assert extract_provided_song(story) == ""


def test_short_brief_echo_is_still_removed():
    idea = "песня маме про сад"
    lyrics = "\n".join(
        [
            "[Verse 1]",
            "песня маме про сад",
            "Розы цветут у старого окна",
            "Свет на кухне горит допоздна",
            "Мы молчим и это не беда",
            "Завтра снова встретимся у сада",
        ]
    )
    cleaned = scrub_idea_echo_from_lyrics(lyrics, idea)
    assert "песня маме про сад" not in cleaned.lower()
    assert "Розы цветут" in cleaned


def test_producer_sings_pasted_song_and_does_not_mine_calm():
    assert parse_idea(_PASTED).mood == "calm"
    fake = _FakeLlm()
    plan, payload = PromptBuilder(fake).build(
        _PASTED,
        genre="",
        mood="",
        lyrics_engine="unified",
    )
    assert len(fake.systems) == 1
    assert "Analyst" in fake.systems[0]
    assert "У дяди дома тихо и тепло" in payload.lyrics
    assert payload.lyrics.count("[Verse") == 2
    assert plan.mood != "calm"
    assert plan.genre == "Pop-Rock"


def test_expert_text_button_returns_the_pasted_song_without_a_model():
    class Boom:
        MODEL_PRO = "yandexgpt"
        MODEL_LITE = "yandexgpt-lite"

        def complete(self, *args, **kwargs):
            raise AssertionError("модель не нужна")

    lyrics = PromptBuilder(Boom()).generate_lyrics(_PASTED, ProductionPlan())
    assert "У дяди дома тихо и тепло" in lyrics
    assert "Совет для генерации" not in lyrics
