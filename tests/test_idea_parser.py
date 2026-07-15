"""Тесты разбора идеи и приоритета настроек UI."""

from backend.services.genre_resolver import infer_genre_from_idea
from backend.services.idea_parser import merge_parsed_with_request, parse_idea


def test_ui_genre_overrides_ballad_in_idea_text():
    """Чип «Реп» важнее слова «баллада» в тексте (без явного «жанр …»)."""
    parsed = parse_idea("лирическая баллада про улицу, в духе Басты")
    genre, mood, artist, *_ = merge_parsed_with_request(
        parsed,
        genre="Реп",
        mood="adventurous",
        artist_ref="",
    )
    assert genre == "Реп"
    assert "genre" in parsed.locked_fields


def test_inline_zhanr_rep_beats_default_ui_pop():
    """«Жанр реп» в AI-продюсере важнее дефолтного чипа Поп."""
    idea = (
        "Песня о городе Тюмень, в честь 440 летия. Жанр реп, стиль Баста, "
        "дуэт, с женским бек вокалом на подпеках. Живой концерт на большом стадионе."
    )
    parsed = parse_idea(idea)
    assert parsed.genre == "Реп"
    assert parsed.genre_inline_lock is True
    assert parsed.artist_ref == "Баста"
    assert parsed.vocal_hint == "duet"
    assert parsed.backing_vocal is True
    assert parsed.backing_vocal_gender == "f"

    genre, mood, artist, vocal, backing, bgender, _ = merge_parsed_with_request(
        parsed,
        genre="Поп",
        mood="uplifting",
        artist_ref="",
        vocal_hint="auto",
        backing_vocal=False,
    )
    assert genre == "Реп"
    assert artist == "Баста"
    assert vocal == "duet"
    assert backing is True
    assert bgender == "f"


def test_ui_artist_ref_overrides_parsed():
    parsed = parse_idea("песня в стиле Кино")
    _, _, artist, *_ = merge_parsed_with_request(
        parsed,
        genre="Рок",
        mood="",
        artist_ref="Баста",
    )
    assert artist == "Баста"
    assert "artist" in parsed.locked_fields


def test_english_rap_rock_anthem_parsed():
    text = (
        "epic Russian rap-rock anthem, live stadium concert recording, "
        "gravelly emotional male rap-singing voice, patriotic hip-hop"
    )
    parsed = parse_idea(text)
    assert parsed.genre == "Реп"
    assert parsed.mood == "adventurous"


def test_idea_genre_used_when_ui_empty():
    parsed = parse_idea("сделай реп про город")
    genre, _, _, *_ = merge_parsed_with_request(
        parsed,
        genre="",
        mood="",
        artist_ref="",
    )
    assert genre == "Реп"


def test_infer_genre_rep_without_yo():
    genre, sub = infer_genre_from_idea("Жанр реп про Тюмень на стадионе")
    assert genre == "Hip-Hop"
    assert "Hip-Hop" in sub or "hip" in sub.lower()
