import random
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from backend.database.db import get_connection, init_db, utc_now
from backend.settings import SESSION_TTL_DAYS


class AuthService:
    COOKIE_NAME = "sf_session"

    def __init__(self) -> None:
        init_db()

    def _expires_at(self) -> str:
        return (datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)).isoformat()

    def get_user_by_session(self, token: str | None) -> dict | None:
        if not token:
            return None
        now = utc_now()
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT u.id, u.email, u.display_name, u.balance, u.created_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = ? AND s.expires_at > ?
                """,
                (token, now),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (token, user_id, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (token, user_id, self._expires_at(), now),
            )
        return token

    def logout(self, token: str) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def _get_or_create_user_by_email(self, email: str) -> dict:
        email = email.strip().lower()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, email, display_name, balance, created_at FROM users WHERE email = ?",
                (email,),
            ).fetchone()
            if row:
                return dict(row)

            user_id = str(uuid.uuid4())
            now = utc_now()
            conn.execute(
                """
                INSERT INTO users (id, email, display_name, balance, created_at)
                VALUES (?, ?, ?, 0, ?)
                """,
                (user_id, email, email.split("@")[0], now),
            )
            identity_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO auth_identities (id, user_id, provider, provider_user_id, metadata_json, created_at)
                VALUES (?, ?, 'email', ?, NULL, ?)
                """,
                (identity_id, user_id, email, now),
            )
            return {
                "id": user_id,
                "email": email,
                "display_name": email.split("@")[0],
                "balance": 0,
                "created_at": now,
            }

    def request_email_code(self, email: str) -> str:
        email = email.strip().lower()
        if "@" not in email or len(email) < 5:
            raise ValueError("Укажите корректный email")

        code = f"{random.randint(100000, 999999)}"
        now = utc_now()
        expires = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO email_auth_codes (email, code, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (email, code, expires, now),
            )
        return code

    def verify_email_code(self, email: str, code: str) -> tuple[dict, str]:
        email = email.strip().lower()
        code = code.strip()
        now = utc_now()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT code, expires_at FROM email_auth_codes WHERE email = ?",
                (email,),
            ).fetchone()
            if not row or row["code"] != code:
                raise ValueError("Неверный код")
            if row["expires_at"] <= now:
                raise ValueError("Код истёк — запросите новый")
            conn.execute("DELETE FROM email_auth_codes WHERE email = ?", (email,))

        user = self._get_or_create_user_by_email(email)
        token = self.create_session(user["id"])
        return user, token

    def login_telegram(
        self,
        *,
        telegram_id: str,
        first_name: str = "",
        username: str = "",
    ) -> tuple[dict, str]:
        if not telegram_id:
            raise ValueError("Telegram ID обязателен")

        display = first_name or username or f"tg_{telegram_id}"
        now = utc_now()
        with get_connection() as conn:
            identity = conn.execute(
                """
                SELECT user_id FROM auth_identities
                WHERE provider = 'telegram' AND provider_user_id = ?
                """,
                (telegram_id,),
            ).fetchone()

            if identity:
                user_id = identity["user_id"]
            else:
                user_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO users (id, email, display_name, balance, created_at)
                    VALUES (?, NULL, ?, 0, ?)
                    """,
                    (user_id, display, now),
                )
                conn.execute(
                    """
                    INSERT INTO auth_identities (id, user_id, provider, provider_user_id, metadata_json, created_at)
                    VALUES (?, ?, 'telegram', ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        user_id,
                        telegram_id,
                        f'{{"username":"{username}"}}',
                        now,
                    ),
                )

            user_row = conn.execute(
                "SELECT id, email, display_name, balance, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()

        user = dict(user_row)
        token = self.create_session(user["id"])
        return user, token