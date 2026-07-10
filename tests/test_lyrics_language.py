"""Проверка определения языка текста песни."""

from backend.utils.text import (
    idea_looks_russian,
    lyrics_look_english,
    resolve_lyrics_language,
)

ENGLISH_LYRICS = """[Verse 1]
We've been through so much, you and I
Through thick and thin, we've learned to fly
With every step, we've grown so strong
Our love has blossomed all along
[Chorus]
Together forever, hand in hand
Through the good times, through the bad"""

RUSSIAN_LYRICS = """[Verse 1]
Мы прошли сквозь дождь и зной
И нашли свой тихий дом
В наших детях свет живой
Мы с тобой идём вдвоём
[Chorus]
Вместе навсегда, рука в руке"""


def test_idea_looks_russian():
    assert idea_looks_russian("О любви, пары живущей давно вместе") is True
    assert idea_looks_russian("A song about love in London") is False


def test_lyrics_look_english_detects_bug_sample():
    assert lyrics_look_english(ENGLISH_LYRICS) is True
    assert lyrics_look_english(RUSSIAN_LYRICS) is False


def test_resolve_lyrics_language_explicit_english():
    code, label, is_default = resolve_lyrics_language(
        "Песня про любовь, но текст на английском"
    )
    assert code == "en"
    assert label == "английском"
    assert is_default is False


def test_resolve_lyrics_language_default_russian():
    code, label, is_default = resolve_lyrics_language(
        "О любви, пары живущей давно вместе"
    )
    assert code == "ru"
    assert is_default is True