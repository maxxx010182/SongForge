import secrets
import uuid

from backend.database.db import get_connection, init_db, utc_now
from backend.settings import GUEST_GENERATION_LIMIT


class GuestService:
    COOKIE_NAME = "sf_guest_id"

    def __init__(self) -> None:
        init_db()

    def new_guest_id(self) -> str:
        return secrets.token_urlsafe(24)

    def touch(self, guest_id: str) -> None:
        now = utc_now()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT guest_id FROM guest_sessions WHERE guest_id = ?",
                (guest_id,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE guest_sessions SET last_seen_at = ? WHERE guest_id = ?",
                    (now, guest_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO guest_sessions (guest_id, generations_used, created_at, last_seen_at)
                    VALUES (?, 0, ?, ?)
                    """,
                    (guest_id, now, now),
                )

    def get_usage(self, guest_id: str) -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT generations_used FROM guest_sessions WHERE guest_id = ?",
                (guest_id,),
            ).fetchone()
        return int(row["generations_used"]) if row else 0

    def remaining(self, guest_id: str) -> int:
        return max(0, GUEST_GENERATION_LIMIT - self.get_usage(guest_id))

    def can_generate(self, guest_id: str) -> bool:
        return self.remaining(guest_id) > 0

    def mark_exhausted(self, guest_id: str) -> None:
        """Закрыть гостевую пробную попытку (например, после выхода из аккаунта)."""
        now = utc_now()
        limit = GUEST_GENERATION_LIMIT
        with get_connection() as conn:
            row = conn.execute(
                "SELECT guest_id FROM guest_sessions WHERE guest_id = ?",
                (guest_id,),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE guest_sessions
                    SET generations_used = ?, last_seen_at = ?
                    WHERE guest_id = ?
                    """,
                    (limit, now, guest_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO guest_sessions (guest_id, generations_used, created_at, last_seen_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (guest_id, limit, now, now),
                )

    def consume_generation(self, guest_id: str) -> None:
        now = utc_now()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT generations_used FROM guest_sessions WHERE guest_id = ?",
                (guest_id,),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE guest_sessions
                    SET generations_used = generations_used + 1, last_seen_at = ?
                    WHERE guest_id = ?
                    """,
                    (now, guest_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO guest_sessions (guest_id, generations_used, created_at, last_seen_at)
                    VALUES (?, 1, ?, ?)
                    """,
                    (guest_id, now, now),
                )

    def link_generation(self, *, guest_id: str, production_id: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE generations SET guest_id = ? WHERE id = ?",
                (guest_id, production_id),
            )