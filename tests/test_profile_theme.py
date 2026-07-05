"""Тесты темы оформления в профиле."""

import uuid

from backend.database.db import get_connection, init_db
from backend.services.profile_service import ProfileService


def _insert_user(*, email: str, display_name: str) -> str:
    user_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (
                id, email, display_name, balance, created_at,
                nickname_confirmed, is_persona, theme
            ) VALUES (?, ?, ?, 0, '2026-07-05T10:00:00', 1, 0, 'burgundy')
            """,
            (user_id, email, display_name),
        )
    return user_id


def test_update_theme_and_reject_unknown():
    init_db()
    svc = ProfileService()
    user_id = _insert_user(email="theme@test.local", display_name="ThemeUser")

    updated = svc.update_theme(user_id=user_id, theme="classic")
    assert updated["theme"] == "classic"

    try:
        svc.update_theme(user_id=user_id, theme="neon")
        raised = False
    except ValueError:
        raised = True
    assert raised

    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))