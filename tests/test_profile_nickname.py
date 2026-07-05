"""Тесты уникальных ников пользователей."""

import uuid

from backend.database.db import get_connection, init_db
from backend.services.profile_service import DisplayNameTakenError, ProfileService


def _insert_user(*, email: str, display_name: str, nickname_confirmed: int = 1) -> str:
    user_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (
                id, email, display_name, balance, created_at,
                nickname_confirmed, is_persona
            ) VALUES (?, ?, ?, 0, '2026-07-05T10:00:00', ?, 0)
            """,
            (user_id, email, display_name, nickname_confirmed),
        )
    return user_id


def test_unique_nickname_rejected():
    init_db()
    svc = ProfileService()
    first_id = _insert_user(email="a@test.local", display_name="Викуся")
    second_id = _insert_user(email="b@test.local", display_name="Другой")

    try:
        svc.update_display_name(user_id=second_id, display_name="Викуся")
        raised = False
    except DisplayNameTakenError:
        raised = True
    assert raised

    updated = svc.update_display_name(user_id=first_id, display_name="Викуся2")
    assert updated["display_name"] == "Викуся2"
    assert int(updated["nickname_confirmed"]) == 1

    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE id IN (?, ?)", (first_id, second_id))