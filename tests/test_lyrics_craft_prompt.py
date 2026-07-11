"""Промпты сонграйтинга — структура и лимиты Suno."""

from backend.services.lyrics_craft_prompt import (
    CLASSIC_LYRICS_SYSTEM,
    LYRICS_MODEL_ATTEMPTS,
    UNIFIED_MODEL_ATTEMPTS,
    UNIFIED_PACKAGE_SYSTEM,
)
from backend.utils.suno_payload import SUNO_STYLE_MAX_LEN, SUNO_TITLE_MAX_LEN


def test_unified_prompt_mentions_craft_and_suno_limits():
    assert "метафор" in UNIFIED_PACKAGE_SYSTEM.lower()
    assert "хук" in UNIFIED_PACKAGE_SYSTEM.lower()
    assert "200" in UNIFIED_PACKAGE_SYSTEM
    assert "3000" in UNIFIED_PACKAGE_SYSTEM
    assert "style_prompt" in UNIFIED_PACKAGE_SYSTEM
    assert "lyrics" in UNIFIED_PACKAGE_SYSTEM
    assert str(SUNO_STYLE_MAX_LEN) in UNIFIED_PACKAGE_SYSTEM


def test_classic_prompt_mentions_craft_without_json():
    assert "метафор" in CLASSIC_LYRICS_SYSTEM.lower()
    assert "JSON" not in CLASSIC_LYRICS_SYSTEM
    assert "[Verse 1]" in CLASSIC_LYRICS_SYSTEM


def test_model_fallback_chains_use_pro_then_lite():
    assert LYRICS_MODEL_ATTEMPTS[0][0] == "yandexgpt"
    assert LYRICS_MODEL_ATTEMPTS[-1][0] == "yandexgpt-lite"
    assert UNIFIED_MODEL_ATTEMPTS[-1][0] == "yandexgpt-lite"


def test_title_limit_matches_suno_constant():
    assert str(SUNO_TITLE_MAX_LEN) in UNIFIED_PACKAGE_SYSTEM