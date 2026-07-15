"""Промпты сонграйтинга — структура, длина ~4 мин, не «что вижу — то пою»."""

from backend.services.lyrics_craft_prompt import (
    CLASSIC_LYRICS_SYSTEM,
    LYRICS_MODEL_ATTEMPTS,
    SCREENPLAY_RETRY_HINT,
    UNIFIED_MODEL_ATTEMPTS,
    UNIFIED_PACKAGE_SYSTEM,
    UNIFIED_SCREENPLAY_RETRY_HINT,
    lyrics_screenplay_user_hint,
)
from backend.utils.suno_payload import SUNO_STYLE_MAX_LEN, SUNO_TITLE_MAX_LEN


def test_unified_prompt_mentions_suno_screenplay_and_limits():
    blob = UNIFIED_PACKAGE_SYSTEM.lower()
    assert "suno studio" in blob or "suno screenplay" in blob or "screenplay" in blob
    assert "delivery" in blob
    assert "200" in UNIFIED_PACKAGE_SYSTEM
    assert "2000" in UNIFIED_PACKAGE_SYSTEM or "4 мин" in UNIFIED_PACKAGE_SYSTEM
    assert "style_prompt" in UNIFIED_PACKAGE_SYSTEM
    assert "lyrics" in UNIFIED_PACKAGE_SYSTEM
    assert str(SUNO_STYLE_MAX_LEN) in UNIFIED_PACKAGE_SYSTEM
    assert "что вижу" in blob or "бриф" in blob


def test_classic_prompt_mentions_screenplay_without_json():
    blob = CLASSIC_LYRICS_SYSTEM.lower()
    assert "suno" in blob
    assert "delivery" in blob
    assert "не копируй" in blob or "не шаблон" in blob or "не копируй тему" in blob
    assert "JSON" not in CLASSIC_LYRICS_SYSTEM
    assert "баллада" in blob or "ballad" in blob
    assert "4" in CLASSIC_LYRICS_SYSTEM


def test_screenplay_hint_adapts_by_genre():
    stadium = lyrics_screenplay_user_hint(
        genre="Pop Rock",
        subgenre="Anthem",
        mood="uplifting",
        energy="high",
        idea="Гимн городу на стадионе",
        backing_vocal=False,
    ).lower()
    assert "stadium" in stadium or "anthem" in stadium or "crowd" in stadium

    ballad = lyrics_screenplay_user_hint(
        genre="Ballad",
        subgenre="Acoustic",
        mood="melancholic",
        energy="low",
        idea="Прощание на вокзале",
        backing_vocal=False,
    ).lower()
    assert "crowd" not in ballad or "без crowd" in ballad
    assert "intimate" in ballad or "спокой" in ballad or "лирич" in ballad


def test_retry_hints_target_full_form():
    hint = SCREENPLAY_RETRY_HINT.lower()
    assert "4" in SCREENPLAY_RETRY_HINT or "структур" in hint
    assert "бриф" in hint or "пересказ" in hint or "хук" in hint
    assert UNIFIED_SCREENPLAY_RETRY_HINT == SCREENPLAY_RETRY_HINT


def test_model_fallback_chains_use_pro_then_lite():
    assert LYRICS_MODEL_ATTEMPTS[0][0] == "yandexgpt"
    assert LYRICS_MODEL_ATTEMPTS[-1][0] == "yandexgpt-lite"
    assert UNIFIED_MODEL_ATTEMPTS[-1][0] == "yandexgpt-lite"


def test_title_limit_matches_suno_constant():
    assert str(SUNO_TITLE_MAX_LEN) in UNIFIED_PACKAGE_SYSTEM
