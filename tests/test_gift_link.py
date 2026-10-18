import uuid

from backend.database.db import get_connection, init_db
from backend.gift_page import render_gift_page
from backend.services.gift_service import GiftService, dedication_line, normalize_occasion


def test_occasion_and_dedication():
    assert normalize_occasion("love") == "love"
    assert normalize_occasion("xxx") == "simple"
    assert dedication_line(occasion="family", from_line="Ирина") == "это тебе · от Ирина"
    assert dedication_line(occasion="simple", from_line="") == ""


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
        dedication="это тебе · от Ирина",
        occasion="family",
        image_url="/cover.jpg",
    )
    assert "Для мамы" in html
    assert "Ты мой свет" in html
    assert "МузПлощадк" not in html
    assert "Лайк" not in html
    assert "/api/gift/abc/listen" in html
