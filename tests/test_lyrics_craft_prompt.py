"""Промпты сонграйтинга — структура и лимиты Suno."""

from backend.services.lyrics_craft_prompt import (
    CLASSIC_LYRICS_SYSTEM,
    LYRICS_MODEL_ATTEMPTS,
    SCREENPLAY_RETRY_HINT,
    UNIFIED_MODEL_ATTEMPTS,
    UNIFIED_PACKAGE_SYSTEM,
    UNIFIED_SCREENPLAY_RETRY_HINT,
)
from backend.utils.suno_payload import SUNO_STYLE_MAX_LEN, SUNO_TITLE_MAX_LEN


def test_unified_prompt_mentions_suno_screenplay_and_limits():
    blob = UNIFIED_PACKAGE_SYSTEM.lower()
    assert "suno studio" in blob or "suno screenplay" in blob
    assert "delivery" in blob
    assert "200" in UNIFIED_PACKAGE_SYSTEM
    assert "3000" in UNIFIED_PACKAGE_SYSTEM
    assert "style_prompt" in UNIFIED_PACKAGE_SYSTEM
    assert "lyrics" in UNIFIED_PACKAGE_SYSTEM
    assert str(SUNO_STYLE_MAX_LEN) in UNIFIED_PACKAGE_SYSTEM


def test_classic_prompt_mentions_screenplay_without_json():
    blob = CLASSIC_LYRICS_SYSTEM.lower()
    assert "suno" in blob
    assert "delivery" in blob
    assert "JSON" not in CLASSIC_LYRICS_SYSTEM
    assert "[Verse 1 -" in CLASSIC_LYRICS_SYSTEM or "gritty rap-sung" in CLASSIC_LYRICS_SYSTEM


def test_retry_hints_target_screenplay_format():
    assert "screenplay" in SCREENPLAY_RETRY_HINT.lower()
    assert UNIFIED_SCREENPLAY_RETRY_HINT == SCREENPLAY_RETRY_HINT


def test_model_fallback_chains_use_pro_then_lite():
    assert LYRICS_MODEL_ATTEMPTS[0][0] == "yandexgpt"
    assert LYRICS_MODEL_ATTEMPTS[-1][0] == "yandexgpt-lite"
    assert UNIFIED_MODEL_ATTEMPTS[-1][0] == "yandexgpt-lite"


def test_title_limit_matches_suno_constant():
    assert str(SUNO_TITLE_MAX_LEN) in UNIFIED_PACKAGE_SYSTEM