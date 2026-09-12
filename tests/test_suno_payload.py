"""Тесты лимитов и нормализации запроса Suno."""

from backend.models import ProductionPlan
from backend.services.suno_input import build_suno_custom_payload
from backend.utils.suno_payload import (
    SUNO_DURATION_MAX,
    SUNO_STYLE_MAX_LEN,
    clamp_suno_duration,
    compact_suno_style,
    sanitize_negative_tags,
    sanitize_suno_title,
)


def test_clamp_duration_caps_eight_minutes():
    assert clamp_suno_duration(480) == SUNO_DURATION_MAX
    assert clamp_suno_duration(0) == 240
    assert clamp_suno_duration(120) == 120


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