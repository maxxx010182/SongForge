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


def _full_lyrics() -> str:
    """Достаточно длинный screenplay для parse (полный QA — на compose)."""
    return (
        "[Intro - soft crowd bed]\n"
        "(эй)\n\n"
        "[Verse 1 - gritty storytelling]\n"
        "Город встает на рассвете\n"
        "Улицы полны огней\n"
        "Сердце бьется в такт ветру\n"
        "Мы идем сквозь все дожди\n"
        "Мосты молчат над рекою\n"
        "Снег рисует белый путь\n"
        "Я храню твой голос рядом\n"
        "Чтобы не сбиться с пути\n\n"
        "[Pre-Chorus - building]\n"
        "Ещё один шаг — и выше\n"
        "Ещё один вдох — и в бой\n\n"
        "[Chorus - stadium singalong]\n"
        "Тюмень — наш дом и свет\n"
        "Звучит в каждом из нас\n"
        "Тюмень — один на всех ответ\n"
        "Мы не сдадимся сейчас\n\n"
        "[Verse 2 - new angle]\n"
        "Вечер кладёт огни на окна\n"
        "Друзья зовут на мост\n"
        "Я меняю страх на силу\n"
        "И собираю новый рост\n"
        "Пусть метель стирает следы\n"
        "Мы рисуем свой маршрут\n"
        "В каждом дворе своя история\n"
        "В каждом сердце — абсолют\n\n"
        "[Pre-Chorus - building]\n"
        "Ещё один шаг — и выше\n"
        "Ещё один вдох — и в бой\n\n"
        "[Chorus - stadium singalong]\n"
        "Тюмень — наш дом и свет\n"
        "Звучит в каждом из нас\n"
        "Тюмень — один на всех ответ\n"
        "Мы не сдадимся сейчас\n\n"
        "[Bridge - strip-back then lift]\n"
        "Если тишина ответит первой\n"
        "Мы не убежим — останемся тут\n"
        "Между ночью и рассветом\n"
        "Выберем шаги вперёд\n\n"
        "[Final Chorus - full band]\n"
        "Тюмень — наш дом и свет\n"
        "Звучит в каждом из нас\n"
        "Тюмень — один на всех ответ\n"
        "Мы не сдадимся сейчас\n"
        "(эй)\n\n"
        "[Outro]\n"
        "Дом и свет…\n"
        "Сейчас."
    )


def test_parse_unified_package_json():
    raw = json.dumps(
        {
            "title": "Тюмень",
            "lyrics": _full_lyrics(),
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
    assert result.lyrics.startswith("[Intro") or result.lyrics.startswith("[Verse 1]")
    assert len(result.style) <= SUNO_STYLE_MAX_LEN
    assert "sung in russian" in result.style.lower()
    assert len(result.lyrics) > 500


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
            "lyrics": _full_lyrics(),
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
