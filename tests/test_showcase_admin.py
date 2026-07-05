"""Тесты админ-витрины: персоны и seed-лайки."""

import uuid

from backend.database.db import get_connection, init_db
from backend.services.showcase_admin_service import ShowcaseAdminService


def _seed_published_track(*, owner_id: str, title: str = "Тестовый хит") -> str:
    library_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_library (
                id, user_id, generation_id, title, variant, audio_url,
                image_url, duration, lyrics, genre, purchased_at, published_at
            ) VALUES (?, ?, ?, ?, 'A', 'https://cdn.example/a.mp3', '', 180, '', 'Pop', ?, ?)
            """,
            (
                library_id,
                owner_id,
                str(uuid.uuid4()),
                title,
                "2026-07-05T10:00:00",
                "2026-07-05T11:00:00",
            ),
        )
    return library_id


def test_personas_and_seed_likes_for_own_track():
    init_db()
    svc = ShowcaseAdminService()
    owner_id = f"owner-{uuid.uuid4()}"

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, balance, created_at, is_persona)
            VALUES (?, 'owner@test.local', 'Владелец', 0, '2026-07-05T10:00:00', 0)
            """,
            (owner_id,),
        )

    created = svc.create_personas(count=5)
    assert len(created) == 5
    assert svc.persona_count() >= 5
    plain_names = {"марина", "алексей", "катя", "денис", "оля", "игорь"}
    for row in created:
        name = (row["display_name"] or "").strip()
        assert len(name) >= 2
        assert name.casefold() not in plain_names

    library_id = _seed_published_track(owner_id=owner_id)
    result = svc.add_seed_likes(
        admin_user_id=owner_id,
        admin_role="admin",
        library_id=library_id,
        count=3,
    )
    assert result["added"] == 3
    assert result["likes"] == 3

    comment = svc.add_seed_comment(
        admin_user_id=owner_id,
        admin_role="admin",
        library_id=library_id,
        persona_id=created[0]["id"],
        text="Очень понравилось!",
    )
    assert comment["author_name"] == created[0]["display_name"]

    tracks = svc.list_showcase_tracks(
        admin_user_id=owner_id,
        admin_role="admin",
        limit=10,
    )
    row = next(t for t in tracks if t["id"] == library_id)
    assert row["likes"] == 3
    assert row["seed_likes"] == 3
    assert row["comments"] == 1

    cleared = svc.clear_seed_engagement(
        admin_user_id=owner_id,
        admin_role="admin",
        library_id=library_id,
    )
    assert cleared["likes_removed"] == 3
    assert cleared["comments_removed"] == 1
    assert cleared["likes"] == 0

    with get_connection() as conn:
        conn.execute("DELETE FROM track_comments WHERE library_id = ?", (library_id,))
        conn.execute("DELETE FROM track_likes WHERE library_id = ?", (library_id,))
        conn.execute("DELETE FROM user_library WHERE id = ?", (library_id,))
        conn.execute("DELETE FROM users WHERE COALESCE(is_persona, 0) = 1")
        conn.execute("DELETE FROM users WHERE id = ?", (owner_id,))


def test_non_owner_cannot_boost_without_super_admin():
    init_db()
    svc = ShowcaseAdminService()
    owner_id = f"owner-{uuid.uuid4()}"
    other_id = f"other-{uuid.uuid4()}"

    with get_connection() as conn:
        for uid, email in ((owner_id, "o@test.local"), (other_id, "x@test.local")):
            conn.execute(
                """
                INSERT INTO users (id, email, display_name, balance, created_at)
                VALUES (?, ?, 'U', 0, '2026-07-05T10:00:00')
                """,
                (uid, email),
            )

    library_id = _seed_published_track(owner_id=owner_id)
    svc.create_personas(count=2)

    try:
        svc.add_seed_likes(
            admin_user_id=other_id,
            admin_role="admin",
            library_id=library_id,
            count=1,
        )
        raised = False
    except PermissionError:
        raised = True
    assert raised

    with get_connection() as conn:
        conn.execute("DELETE FROM user_library WHERE id = ?", (library_id,))
        conn.execute("DELETE FROM users WHERE id IN (?, ?)", (owner_id, other_id))
        conn.execute("DELETE FROM users WHERE COALESCE(is_persona, 0) = 1")