"""Тесты unified-движка (парсинг пакета title + lyrics + style)."""

import json

from backend.models import MusicAnalysis
from backend.services.suno_package_composer import SunoPackageComposer
from backend.utils.suno_payload import SUNO_STYLE_MAX_LEN


def _sample_analysis() -> MusicAnalysis:
    return MusicAnalysis(
        genre="Rock",
        subgenre="Rap-Rock",
        mood="uplifting",
        bpm=128,
        energy="high",
        idea="Гимн про Тюмень",
    )


def test_parse_unified_package_json():
    raw = json.dumps(
        {
            "title": "Тюмень",
            "lyrics": (
                "[Verse 1]\n"
                "Город встает на рассвете\n"
                "Улицы полны огней\n"
                "Сердце бьется в такт ветру\n"
                "Мы идем сквозь все дожди\n\n"
                "[Chorus]\n"
                "Тюмень — наш дом и свет\n"
                "Звучит в каждом из нас\n"
                "Тюмень — один на всех ответ\n"
                "Мы не сдадимся сейчас"
            ),
            "style_prompt": (
                "Russian rap-rock stadium anthem, gravelly male rap vocals, "
                "distorted guitars, live crowd energy, bass-heavy, wide stereo, "
                "sung in Russian, native Russian vocals"
            ),
        },
        ensure_ascii=False,
    )
    result = SunoPackageComposer._parse_response(
        raw,
        idea="Гимн про Тюмень, stadium rap-rock",
        analysis=_sample_analysis(),
    )
    assert result is not None
    assert result.title == "Тюмень"
    assert result.lyrics.startswith("[Verse 1]")
    assert len(result.style) <= SUNO_STYLE_MAX_LEN
    assert "sung in russian" in result.style.lower()


def test_ensure_structure_prepends_verse():
    fixed = SunoPackageComposer._ensure_structure_start(
        "[Crowd cheering]\nМы кричим в унисон"
    )
    assert fixed.startswith("[Verse 1]")
    assert "[Crowd cheering]" in fixed


def test_reject_stage_direction_title():
    raw = json.dumps(
        {
            "title": "[Crowd noise, stadium ambience]",
            "lyrics": (
                "[Verse 1]\n"
                "Строка один с образом\n"
                "Строка два с рифмой тут\n"
                "Строка три продолжает мысль\n"
                "Строка четыре в ритм вступ\n\n"
                "[Chorus]\n"
                "Припев короткий и яркий\n"
                "Слушай сердцем без преград\n"
                "Мы поем его ударно\n"
                "Это наш главный старт"
            ),
            "style_prompt": (
                "stadium rock anthem, male vocals, drums, "
                "sung in Russian, native Russian vocals"
            ),
        },
        ensure_ascii=False,
    )
    result = SunoPackageComposer._parse_response(
        raw,
        idea="Гимн про Тюмень",
        analysis=_sample_analysis(),
    )
    assert result is not None
    assert result.title == "Тюмень"
    assert "[" not in result.title