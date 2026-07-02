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


class ProfileService:
    def __init__(self) -> None:
        init_db()
        AVATARS_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _normalize_display_name(name: str) -> str:
        cleaned = re.sub(r"\s+", " ", name.strip())
        if len(cleaned) < 2:
            raise ValueError("Имя должно быть от 2 до 40 символов")
        if len(cleaned) > 40:
            raise ValueError("Имя не длиннее 40 символов")
        return cleaned

    def get_user(self, user_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, email, display_name, balance, created_at, avatar_url
                FROM users WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_display_name(self, *, user_id: str, display_name: str) -> dict:
        name = self._normalize_display_name(display_name)
        with get_connection() as conn:
            cur = conn.execute(
                "UPDATE users SET display_name = ? WHERE id = ?",
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