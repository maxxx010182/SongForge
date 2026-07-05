"""Тесты лимитов и нормализации запроса Suno."""

from backend.utils.suno_payload import (
    SUNO_STYLE_MAX_LEN,
    compact_suno_style,
    sanitize_negative_tags,
    sanitize_suno_title,
)


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