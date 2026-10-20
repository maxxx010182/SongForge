"""Ссылка-подарок: кому, от кого, тон по поводу."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from backend.database.db import get_connection

OCCASIONS = ("family", "love", "birthday", "simple", "other")
OCCASION_DEFAULTS = {
    "family": {"to": "Для мамы"},
    "love": {"to": "Для тебя"},
    "birthday": {"to": "С днём рождения"},
    "simple": {"to": "Тебе"},
    "other": {"to": "Тебе"},
}
TO_MAX = 200
FROM_MAX = 80


def normalize_occasion(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value in OCCASIONS:
        return value
    return "simple"


def _clean_line(raw: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (raw or "").strip())
    return text[:limit]


def _clean_wish(raw: str, limit: int) -> str:
    lines: list[str] = []
    for part in (raw or "").replace("\r\n", "\n").split("\n"):
        line = re.sub(r" +", " ", part.strip())
        if line:
            lines.append(line)
    return "\n".join(lines)[:limit]


def dedication_line(*, occasion: str, from_line: str) -> str:
    """Подпись на карточке — ровно строка «от кого»."""
    _ = occasion
    return _clean_line(from_line, FROM_MAX)


def _row_to_dict(row) -> dict:
    occasion = normalize_occasion(row["occasion"])
    to_line = (row["to_line"] or "").strip() or OCCASION_DEFAULTS[occasion]["to"]
    from_line = (row["from_line"] or "").strip()
    return {
        "id": row["id"],
        "library_id": row["library_id"],
        "user_id": row["user_id"],
        "occasion": occasion,
        "to_line": to_line,
        "from_line": from_line,
        "dedication": dedication_line(occasion=occasion, from_line=from_line),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"] if "updated_at" in row.keys() else "",
    }


class GiftService:
    def get_by_id(self, gift_id: str) -> dict | None:
        gid = (gift_id or "").strip()
        if not gid:
            return None
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM gift_links WHERE id = ?",
                (gid,),
            ).fetchone()
        if not row:
            return None
        return _row_to_dict(row)

    def get_for_library(self, *, user_id: str, library_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM gift_links
                WHERE user_id = ? AND library_id = ?
                """,
                (user_id, library_id),
            ).fetchone()
        if not row:
            return None
        return _row_to_dict(row)

    def upsert(
        self,
        *,
        user_id: str,
        library_id: str,
        occasion: str,
        to_line: str,
        from_line: str,
    ) -> dict:
        occasion = normalize_occasion(occasion)
        to_line = _clean_wish(to_line, TO_MAX) or OCCASION_DEFAULTS[occasion]["to"]
        from_line = _clean_line(from_line, FROM_MAX)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        existing = self.get_for_library(user_id=user_id, library_id=library_id)
        gift_id = existing["id"] if existing else str(uuid.uuid4())
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO gift_links (
                    id, library_id, user_id, occasion, to_line, from_line,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(library_id) DO UPDATE SET
                    occasion = excluded.occasion,
                    to_line = excluded.to_line,
                    from_line = excluded.from_line,
                    updated_at = excluded.updated_at
                """,
                (
                    gift_id,
                    library_id,
                    user_id,
                    occasion,
                    to_line,
                    from_line,
                    existing["created_at"] if existing else now,
                    now,
                ),
            )
        saved = self.get_for_library(user_id=user_id, library_id=library_id)
        if not saved:
            raise RuntimeError("Не удалось сохранить ссылку-подарок")
        return saved
