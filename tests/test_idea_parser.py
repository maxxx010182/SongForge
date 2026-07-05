"""Тесты разбора идеи и приоритета настроек UI."""

from backend.services.idea_parser import merge_parsed_with_request, parse_idea


def test_ui_genre_overrides_ballad_in_idea_text():
    parsed = parse_idea("лирическая баллада про улицу, реп в духе Басты")
    genre, mood, artist, *_ = merge_parsed_with_request(
        parsed,
        genre="Реп",
        mood="adventurous",
        artist_ref="",
    )
    assert genre == "Реп"
    assert "genre" in parsed.locked_fields


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