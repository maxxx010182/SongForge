import re
import uuid
from pathlib import Path

from backend.database.db import get_connection, init_db, utc_now
from backend.settings import AVATARS_DIR, MAX_AVATAR_BYTES

_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
_MIME_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
_DISPLAY_NAME_FORBIDDEN = re.compile(r"[@<>]")
VALID_THEMES = frozenset({"classic", "burgundy", "olive", "obsidian"})
DEFAULT_THEME = "burgundy"


class DisplayNameTakenError(ValueError):
    """Ник уже занят другим пользователем или персоной."""


class ProfileService:
    def __init__(self) -> None:
        init_db()
        AVATARS_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _normalize_display_name(name: str) -> str:
        cleaned = re.sub(r"\s+", " ", name.strip())
        if len(cleaned) < 2:
            raise ValueError("Ник — от 2 до 40 символов")
        if len(cleaned) > 40:
            raise ValueError("Ник не длиннее 40 символов")
        if _DISPLAY_NAME_FORBIDDEN.search(cleaned):
            raise ValueError("Ник не должен содержать @ и служебные символы")
        return cleaned

    def _is_display_name_taken(
        self,
        conn,
        *,
        display_name: str,
        exclude_user_id: str | None = None,
    ) -> bool:
        params: list = [display_name]
        extra = ""
        if exclude_user_id:
            extra = " AND id != ?"
            params.append(exclude_user_id)
        row = conn.execute(
            f"""
            SELECT id FROM users
            WHERE LOWER(display_name) = LOWER(?)
            {extra}
            LIMIT 1
            """,
            params,
        ).fetchone()
        return row is not None

    def is_nickname_available(
        self,
        *,
        user_id: str,
        display_name: str,
    ) -> bool:
        name = self._normalize_display_name(display_name)
        with get_connection() as conn:
            if self._is_display_name_taken(
                conn, display_name=name, exclude_user_id=user_id
            ):
                return False
        return True

    def get_user(self, user_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, email, display_name, balance, created_at, avatar_url,
                       COALESCE(nickname_confirmed, 0) AS nickname_confirmed,
                       COALESCE(NULLIF(TRIM(theme), ''), ?) AS theme
                FROM users WHERE id = ?
                """,
                (DEFAULT_THEME, user_id),
            ).fetchone()
        return dict(row) if row else None

    def update_theme(self, *, user_id: str, theme: str) -> dict:
        theme_id = (theme or "").strip().lower()
        if theme_id not in VALID_THEMES:
            raise ValueError("Неизвестная тема оформления")
        with get_connection() as conn:
            persona = conn.execute(
                "SELECT id FROM users WHERE id = ? AND COALESCE(is_persona, 0) = 1",
                (user_id,),
            ).fetchone()
            if persona:
                raise ValueError("Персоны не редактируют профиль")
            cur = conn.execute(
                "UPDATE users SET theme = ? WHERE id = ?",
                (theme_id, user_id),
            )
            if cur.rowcount == 0:
                raise ValueError("Пользователь не найден")
        user = self.get_user(user_id)
        if not user:
            raise ValueError("Пользователь не найден")
        return user

    def update_display_name(self, *, user_id: str, display_name: str) -> dict:
        name = self._normalize_display_name(display_name)
        with get_connection() as conn:
            persona = conn.execute(
                "SELECT id FROM users WHERE id = ? AND COALESCE(is_persona, 0) = 1",
                (user_id,),
            ).fetchone()
            if persona:
                raise ValueError("Персоны не редактируют профиль")

            if self._is_display_name_taken(
                conn, display_name=name, exclude_user_id=user_id
            ):
                raise DisplayNameTakenError("Этот ник уже занят — придумайте другой")

            cur = conn.execute(
                """
                UPDATE users
                SET display_name = ?, nickname_confirmed = 1
                WHERE id = ?
                """,
                (name, user_id),
            )
            if cur.rowcount == 0:
                raise ValueError("Пользователь не найден")
        user = self.get_user(user_id)
        if not user:
            raise ValueError("Пользователь не найден")
        return user

    def save_avatar(
        self,
        *,
        user_id: str,
        content: bytes,
        filename: str = "",
        content_type: str = "",
    ) -> dict:
        if not content:
            raise ValueError("Файл пустой")
        if len(content) > MAX_AVATAR_BYTES:
            raise ValueError("Файл слишком большой (макс. 2 МБ)")

        ext = Path(filename or "").suffix.lower()
        if ext not in _ALLOWED_EXT and content_type in _MIME_EXT:
            ext = _MIME_EXT[content_type]
        if ext == ".jpeg":
            ext = ".jpg"
        if ext not in _ALLOWED_EXT:
            raise ValueError("Допустимы JPG, PNG или WebP")

        for old in AVATARS_DIR.glob(f"{user_id}.*"):
            if old.is_file():
                old.unlink(missing_ok=True)

        stored_name = f"{user_id}{ext}"
        target = AVATARS_DIR / stored_name
        target.write_bytes(content)

        avatar_url = f"/uploads/avatars/{stored_name}?v={uuid.uuid4().hex[:8]}"
        with get_connection() as conn:
            cur = conn.execute(
                "UPDATE users SET avatar_url = ? WHERE id = ?",
                (avatar_url, user_id),
            )
            if cur.rowcount == 0:
                target.unlink(missing_ok=True)
                raise ValueError("Пользователь не найден")

        user = self.get_user(user_id)
        if not user:
            raise ValueError("Пользователь не найден")
        return user