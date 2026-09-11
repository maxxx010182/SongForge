"""«Похожее на хиты»: живые треки МузПлощадки и промпт генерации."""

import uuid

from fastapi.testclient import TestClient

from backend.app import app
from backend.database.db import get_connection, init_db
from backend.services.cabinet_service import compose_similar_idea

client = TestClient(app)


def test_compose_similar_idea_uses_prompt_not_title():
    text = compose_similar_idea(
        idea="Песня маме на день рождения, тепло, гитара",
        style="acoustic pop, warm female vocal",
        genre="Pop",
    )
    assert "Песня маме на день рождения" in text
    assert "acoustic pop" in text
    assert "в стиле" not in text.lower()


def test_compose_similar_idea_falls_back_to_genre():
    text = compose_similar_idea(genre="Рок")
    assert "Рок" in text
    assert "в стиле" not in text.lower()


def test_compose_similar_idea_skips_duplicate_style():
    text = compose_similar_idea(
        idea="Тёплый поп, style: acoustic pop",
        style="acoustic pop",
    )
    assert text.count("acoustic pop") == 1


def test_explore_similar_idea_from_generation():
    init_db()
    owner_id = f"owner-{uuid.uuid4()}"
    gen_id = f"gen-{uuid.uuid4()}"
    library_id = str(uuid.uuid4())
    idea = "Лиричная песня подруге про ночной город и тёплый свет окон"
    style = "soft pop, gentle piano, female vocal"

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, balance, created_at)
            VALUES (?, 'hits@test.local', 'Хитмейкер', 0, '2026-09-11T10:00:00')
            """,
            (owner_id,),
        )
        conn.execute(
            """
            INSERT INTO generations (
                id, created_at, status, idea, style, title, user_id
            ) VALUES (?, '2026-09-11T10:00:00', 'completed', ?, ?, 'Ночной свет', ?)
            """,
            (gen_id, idea, style, owner_id),
        )
        conn.execute(
            """
            INSERT INTO user_library (
                id, user_id, generation_id, title, variant, audio_url,
                image_url, duration, lyrics, genre, purchased_at, published_at
            ) VALUES (?, ?, ?, 'Ночной свет', 'A', 'https://cdn.example/a.mp3',
                      '', 180, '', 'Поп', '2026-09-11T10:00:00', '2026-09-11T11:00:00')
            """,
            (library_id, owner_id, gen_id),
        )

    try:
        response = client.get("/api/explore")
        assert response.status_code == 200
        tracks = response.json()
        row = next(t for t in tracks if t["id"] == library_id)
        assert row["title"] == "Ночной свет"
        assert idea in row["similar_idea"]
        assert "soft pop" in row["similar_idea"]
        assert "Зиверт" not in row["similar_idea"]
        assert "в стиле «Ночной свет»" not in row["similar_idea"]
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM user_library WHERE id = ?", (library_id,))
            conn.execute("DELETE FROM generations WHERE id = ?", (gen_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (owner_id,))


def test_index_hits_are_not_famous_artists():
    html = client.get("/").text
    assert "HIT_IDEAS" not in html
    assert "name:'Зиверт'" not in html
    assert "community-similar-btn" in html
    assert "similar_idea" in html
    assert "exploreTracks" in html
