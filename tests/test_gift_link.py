import io
import uuid
from pathlib import Path

from PIL import Image

from backend.database.db import get_connection, init_db
from backend.gift_page import render_gift_page
from backend.og_image import build_gift_og_jpeg
from backend.services.gift_service import (
    GiftService,
    _clean_wish,
    dedication_line,
    normalize_occasion,
)

ROOT = Path(__file__).resolve().parents[1]


def test_occasion_and_dedication():
    assert normalize_occasion("love") == "love"
    assert normalize_occasion("other") == "other"
    assert normalize_occasion("xxx") == "simple"
    assert dedication_line(occasion="family", from_line="Ирина") == "Ирина"
    assert dedication_line(occasion="birthday", from_line="С любовью, Ира") == "С любовью, Ира"
    assert dedication_line(occasion="simple", from_line="") == ""
    assert _clean_wish("Мама\n  спасибо что ты есть  ", 200) == "Мама\nспасибо что ты есть"


def test_upsert_gift_keeps_same_url():
    init_db()
    user_id = str(uuid.uuid4())
    library_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_library (
                id, user_id, generation_id, title, variant, audio_url,
                image_url, duration, lyrics, genre, purchased_at
            ) VALUES (?, ?, ?, 'Тест', 'A', 'x.mp3', '', 120, '', 'pop', datetime('now'))
            """,
            (library_id, user_id, str(uuid.uuid4())),
        )
    svc = GiftService()
    first = svc.upsert(
        user_id=user_id,
        library_id=library_id,
        occasion="family",
        to_line="Для мамы",
        from_line="Ира",
    )
    second = svc.upsert(
        user_id=user_id,
        library_id=library_id,
        occasion="love",
        to_line="Для тебя",
        from_line="Ира",
    )
    assert first["id"] == second["id"]
    assert second["occasion"] == "love"
    assert second["to_line"] == "Для тебя"
    assert second["dedication"] == "Ира"
    with get_connection() as conn:
        conn.execute("DELETE FROM gift_links WHERE library_id = ?", (library_id,))
        conn.execute("DELETE FROM user_library WHERE id = ?", (library_id,))


def test_gift_page_has_heading_not_likes():
    html = render_gift_page(
        site_url="https://sozdaipesnu.ru",
        gift_id="abc",
        title="Ты мой свет",
        to_line="Для мамы",
        from_line="Ирина",
        dedication="Ирина",
        occasion="family",
        image_url="/cover.jpg",
    )
    assert "Для мамы" in html
    assert "Ты мой свет" in html
    assert "Ирина" in html
    assert "песню собрали для тебя" not in html
    assert "это тебе · от" not in html
    assert "МузПлощадк" not in html
    assert "Лайк" not in html
    assert "/api/gift/abc/listen" in html
    assert "/assets/gift/family.jpg" in html
    assert "/assets/gift/family-wide.jpg" in html
    assert "@media (min-width:860px)" in html
    assert "@media (min-width:768px)" in html
    assert 'class="sign "' in html or 'class="sign">' in html or 'class="sign  "' in html


def test_gift_page_hides_empty_signature():
    html = render_gift_page(
        site_url="https://sozdaipesnu.ru",
        gift_id="abc",
        title="Песня",
        to_line="Тебе",
        from_line="",
        dedication="",
        occasion="simple",
        image_url="",
    )
    assert "sign is-empty" in html
    assert "песню собрали" not in html


def test_gift_backgrounds_exist():
    for name in (
        "birthday.jpg",
        "birthday-wide.jpg",
        "love.jpg",
        "love-wide.jpg",
        "family.jpg",
        "family-wide.jpg",
        "simple.jpg",
        "simple-wide.jpg",
    ):
        path = ROOT / "assets" / "gift" / name
        assert path.is_file() and path.stat().st_size > 1000, name


def test_other_occasion_uses_simple_background():
    html = render_gift_page(
        site_url="https://sozdaipesnu.ru",
        gift_id="abc",
        title="Песня",
        to_line="На свадьбу вам",
        from_line="Ира",
        dedication="Ира",
        occasion="other",
        image_url="",
    )
    assert "/assets/gift/simple.jpg" in html
    assert "/assets/gift/simple-wide.jpg" in html
    assert "На свадьбу вам" in html
    assert "white-space:pre-wrap" in html


def test_composer_copy_in_index():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "Половинке" in html
    assert "Любимому" not in html
    assert "Другой повод" in html
    assert "Имя адресата и пожелание" in html
    assert 'id="giftToInput"' in html
    assert "<textarea" in html


def test_gift_og_card_is_1200x630_with_greeting():
    jpeg = build_gift_og_jpeg(
        occasion="birthday",
        to_line="С днём рождения",
        from_line="Ира",
        title="Ты мой свет",
        cover_url="",
        fallback_path=ROOT / "assets" / "logo_new.png",
    )
    im = Image.open(io.BytesIO(jpeg))
    assert im.size == (1200, 630)
    assert im.format == "JPEG"
    assert len(jpeg) > 8000
