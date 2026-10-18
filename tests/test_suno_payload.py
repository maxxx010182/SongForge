"""Тесты лимитов и нормализации запроса Suno."""

from backend.models import ProductionPlan
from backend.services.suno_input import build_suno_custom_payload
from backend.utils.suno_payload import (
    SUNO_DURATION_DEFAULT,
    SUNO_DURATION_LONG,
    SUNO_DURATION_MAX,
    SUNO_STYLE_MAX_LEN,
    clamp_suno_duration,
    compact_suno_style,
    duration_from_lyrics,
    sanitize_negative_tags,
    sanitize_suno_title,
)


def test_clamp_duration_caps_eight_minutes():
    assert clamp_suno_duration(480) == SUNO_DURATION_MAX
    assert clamp_suno_duration(0) == 240
    assert clamp_suno_duration(120) == 120


def _sung_body(char_count: int) -> str:
    line = "Строка куплета про наши дни"
    lines = ["[Verse 1]"]
    filled = 0
    while filled < char_count:
        lines.append(line)
        filled += len(line)
    lines.append("[Chorus]")
    lines.append("Это припев")
    return "\n".join(lines)


def test_duration_from_lyrics_normal_stays_four_minutes():
    lyrics = _sung_body(1800)
    assert duration_from_lyrics(lyrics) == SUNO_DURATION_DEFAULT


def test_duration_from_lyrics_long_goes_five_then_six():
    assert duration_from_lyrics(_sung_body(2300)) == SUNO_DURATION_LONG
    assert duration_from_lyrics(_sung_body(3200)) == SUNO_DURATION_MAX


def test_duration_from_lyrics_ignores_section_tags():
    tags = "\n".join(["[Verse 1 - soft intimate vocal]"] * 80)
    body = _sung_body(1000)
    assert duration_from_lyrics(tags + "\n" + body) == SUNO_DURATION_DEFAULT


def test_duration_from_lyrics_user_minutes_win():
    long_lyrics = _sung_body(4000)
    assert duration_from_lyrics(long_lyrics, requested_sec=180) == 180
    assert duration_from_lyrics(long_lyrics, requested_sec=480) == SUNO_DURATION_MAX


def test_duration_from_lyrics_kids_and_instrumental_stay_four():
    long_lyrics = _sung_body(4000)
    assert (
        duration_from_lyrics(long_lyrics, idea="колыбельная для малыша")
        == SUNO_DURATION_DEFAULT
    )
    assert (
        duration_from_lyrics(long_lyrics, instrumental=True)
        == SUNO_DURATION_DEFAULT
    )


def test_instrumental_payload_has_no_lyrics():
    plan = ProductionPlan(instrumental=True, duration_sec=360)
    payload = build_suno_custom_payload(
        lyrics="should not go",
        style="lo-fi house",
        title="Night drive",
        plan=plan,
    )
    assert payload["instrumental"] is True
    assert payload["prompt"] == ""


def test_compact_style_dedupes_and_limits():
    raw = (
        "rap, rock, rap, stadium, live, drums, "
        "sung in Russian, native Russian vocals, "
        "distorted guitar, orchestral strings, crowd, "
        "male and female duet, hip-hop, modern hip-hop, "
        "uplifting mood, 120 BPM, high energy, bass-heavy"
    )
    out = compact_suno_style(raw)
    assert len(out) <= SUNO_STYLE_MAX_LEN
    assert "rap" in out.lower()
    assert out.lower().count("rap") == 1


def test_sanitize_title_rejects_stage_direction():
    title = sanitize_suno_title(
        "[Crowd noise, stadium ambience]",
        idea="Гимн про Тюмень, stadium rap-rock",
    )
    assert title == "Тюмень"
    assert "[" not in title


def test_sanitize_negative_tags_keeps_rock_stadium():
    style = "Russian rap-rock stadium anthem, distorted guitar, crowd singalong"
    neg = sanitize_negative_tags(
        "unwanted noise, distortion, clipping, screaming, poor mix",
        style,
        "Rock",
    )
    assert "distortion" not in neg.lower()
    assert "screaming" not in neg.lower()
    assert "poor mix" in neg.lower()