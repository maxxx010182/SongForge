"""Универсальное следование жанру из идеи (не только рэп)."""

from backend.models import ProductionPlan
from backend.services.genre_resolver import infer_genre_from_idea
from backend.services.idea_parser import merge_parsed_with_request, parse_idea
from backend.services.style_enforcer import enforce_style


def test_infer_jazz_rock_metal_not_only_rap():
    assert infer_genre_from_idea("песня в стиле джаз")[0] == "Jazz"
    assert infer_genre_from_idea("мощный рок про дорогу")[0] == "Rock"
    assert infer_genre_from_idea("тяжёлый металл")[0] == "Metal"
    assert infer_genre_from_idea("жанр реп про город")[0] == "Hip-Hop"
    assert infer_genre_from_idea("электронная танцевальная")[0] == "Electronic"


def test_default_ui_pop_does_not_override_idea_jazz():
    parsed = parse_idea("Сделай джазовую композицию про дождь в городе")
    genre, *_ = merge_parsed_with_request(
        parsed,
        genre="Поп",
        mood="uplifting",
        artist_ref="",
    )
    assert genre in ("Jazz", "Джаз") or "jazz" in genre.lower() or genre == "Jazz"


def test_default_ui_pop_does_not_override_idea_rock():
    parsed = parse_idea("Рок-баллада про ночной поезд")
    genre, *_ = merge_parsed_with_request(
        parsed,
        genre="Поп",
        mood="",
        artist_ref="",
    )
    g = genre.lower()
    assert "rock" in g or "рок" in g or genre == "Rock"


def test_explicit_ui_chip_beats_idea_keyword():
    """Явный чип «Джаз» важнее слова «реп» в тексте (не дефолт-поп)."""
    parsed = parse_idea("немного репа в куплете, но в целом спокойно")
    genre, *_ = merge_parsed_with_request(
        parsed,
        genre="Джаз",
        mood="",
        artist_ref="",
    )
    assert genre == "Джаз"


def test_enforce_style_jazz_strips_pop_head():
    plan = ProductionPlan(
        genre="Jazz",
        subgenre="Contemporary Jazz",
        mood="calm",
        bpm=90,
        energy="low",
        instruments=["piano", "upright bass", "drums"],
        atmosphere="smoky club",
        production_style="warm live room",
        vocal="male",
        vocal_description="smooth male vocals",
    )
    out = enforce_style(
        "Modern Pop, uplifting, synth, powerful melodic vocals, radio-ready polished mix",
        plan,
    ).lower()
    assert "jazz" in out or "contemporary jazz" in out
    # не должен остаться «modern pop» как ведущий чужой жанр
    assert not out.startswith("modern pop")


def test_enforce_style_rock_not_forced_rap_delivery():
    plan = ProductionPlan(
        genre="Rock",
        subgenre="Alternative Rock",
        mood="uplifting",
        bpm=120,
        energy="high",
        instruments=["electric guitar", "drums", "bass"],
        atmosphere="live",
        production_style="raw rock mix",
        vocal="male",
        vocal_description="gritty male vocals",
    )
    out = enforce_style("Modern Pop, soft synth", plan).lower()
    assert "rock" in out
    assert "rap delivery" not in out
