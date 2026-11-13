"""Поиск человека в админке: русское имя, почта и номер бота."""

import uuid

from backend.database.db import get_connection, init_db
from backend.services.admin_service import AdminService


def test_admin_finds_user_by_any_letter_case_mail_and_bot_number():
    init_db()
    user_id = f"find-{uuid.uuid4()}"
    other_id = f"mail-{uuid.uuid4()}"
    persona_id = f"persona-{uuid.uuid4()}"
    bot_number = "900100200"
    now = "2026-11-13T08:20:00"
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, balance, created_at, is_persona)
            VALUES (?, '', 'ПЕСЕЛЬНИК', 3, ?, 0)
            """,
            (user_id, now),
        )
        conn.execute(
            """
            INSERT INTO auth_identities (
                id, user_id, provider, provider_user_id, created_at
            ) VALUES (?, ?, 'max', ?, ?)
            """,
            (f"id-{user_id}", user_id, bot_number, now),
        )
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, balance, created_at, is_persona)
            VALUES (?, 'note-finder@test.local', 'Почта', 1, ?, 0)
            """,
            (other_id, now),
        )
        conn.execute(
            """
            INSERT INTO users (
                id, email, display_name, balance, created_at, is_persona
            ) VALUES (?, '', 'ПЕСЕЛЬНИК', 0, ?, 1)
            """,
            (persona_id, now),
        )
    try:
        svc = AdminService()
        by_lower = svc.search_users(q="песельник")
        by_upper = svc.search_users(q="ПЕСЕЛЬНИК")
        by_part = svc.search_users(q="песел")
        by_bot = svc.search_users(q=bot_number)
        by_mail = svc.search_users(q="note-finder")
        ids = {row["id"] for row in by_lower}
        assert user_id in ids
        assert persona_id not in ids
        assert {row["id"] for row in by_upper} == ids
        assert user_id in {row["id"] for row in by_part}
        assert {row["id"] for row in by_bot} == {user_id}
        assert {row["id"] for row in by_mail} == {other_id}
        assert by_lower[0]["balance"] == 3 or any(
            row["balance"] == 3 and row["id"] == user_id for row in by_lower
        )
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM auth_identities WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id IN (?, ?, ?)", (user_id, other_id, persona_id))
