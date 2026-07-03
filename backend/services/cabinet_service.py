import json
import uuid

from backend.database.db import get_connection, init_db, utc_now
from backend.services.audio_access_service import AudioAccessService


class CabinetService:
    def __init__(self) -> None:
        init_db()

    def _generation_to_history_item(self, row) -> dict:
        plan = json.loads(row["plan_json"] or "{}")
        genre = plan.get("genre", "")
        return {
            "id": row["id"],
            "title": row["title"] or "Без названия",
            "status": row["status"],
            "created_at": row["created_at"],
            "genre": genre,
            "purchased": bool(row["purchased"]),
            "has_preview_a": bool(row["music_url_a"]),
            "has_preview_b": bool(row["music_url_b"]),
            "image_url_a": row["image_url_a"] or row["image_url_b"],
            "image_url_b": row["image_url_b"] or row["image_url_a"],
        }

    def get_history_preview(
        self, *, user_id: str, generation_id: str, variant: str
    ) -> dict:
        variant_key = variant.strip().lower()
        if variant_key not in {"a", "b"}:
            raise ValueError("Неверный вариант")

        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM generations WHERE id = ? AND user_id = ?",
                (generation_id, user_id),
            ).fetchone()

        if not row:
            raise ValueError("Генерация не найдена")
        if row["purchased"]:
            raise ValueError("Трек уже куплен — откройте фонотеку")
        if row["status"] != "success":
            raise ValueError("Генерация ещё не готова")

        has_url = row["music_url_b"] if variant_key == "b" else row["music_url_a"]
        if not has_url:
            raise ValueError("Аудио не найдено")

        image_url = (
            row["image_url_b"] if variant_key == "b" else row["image_url_a"]
        ) or row["image_url_a"] or row["image_url_b"]

        variant_index = 1 if variant_key == "b" else 0
        return {
            "preview_url": AudioAccessService.preview_path(
                generation_id, variant_index
            ),
            "preview_limit_sec": 30,
            "title": row["title"] or "Без названия",
            "image_url": image_url,
        }

    def list_history(self, user_id: str) -> list[dict]:
        """Variant A: unpurchased generations only."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM generations
                WHERE user_id = ? AND purchased = 0 AND status = 'success'
                ORDER BY created_at DESC
                LIMIT 50
                """,
                (user_id,),
            ).fetchall()
        return [self._generation_to_history_item(r) for r in rows]

    def get_library_item(self, *, user_id: str, library_id: str):
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM user_library WHERE id = ? AND user_id = ?",
                (library_id, user_id),
            ).fetchone()

    def list_library(self, user_id: str) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM user_library
                WHERE user_id = ?
                ORDER BY purchased_at DESC
                LIMIT 100
                """,
                (user_id,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "generation_id": r["generation_id"],
                "title": r["title"],
                "variant": r["variant"],
                "audio_url": r["audio_url"],
                "image_url": r["image_url"],
                "duration": r["duration"],
                "lyrics": r["lyrics"] or "",
                "genre": r["genre"] or "",
                "purchased_at": r["purchased_at"],
                "published_at": r["published_at"],
                "likes": int(r["likes"] or 0),
            }
            for r in rows
        ]

    def publish_library_track(self, *, user_id: str, library_id: str) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM user_library WHERE id = ? AND user_id = ?",
                (library_id, user_id),
            ).fetchone()
            if not row:
                raise ValueError("Трек не найден в фонотеке")
            if row["published_at"]:
                raise ValueError("Трек уже опубликован")
            now = utc_now()
            conn.execute(
                "UPDATE user_library SET published_at = ? WHERE id = ?",
                (now, library_id),
            )
        return {"success": True, "published_at": now, "message": "Трек опубликован"}

    def unpublish_library_track(self, *, user_id: str, library_id: str) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM user_library WHERE id = ? AND user_id = ?",
                (library_id, user_id),
            ).fetchone()
            if not row:
                raise ValueError("Трек не найден в фонотеке")
            if not row["published_at"]:
                raise ValueError("Трек не опубликован")
            conn.execute(
                "UPDATE user_library SET published_at = NULL WHERE id = ?",
                (library_id,),
            )
        return {"success": True, "published_at": None, "message": "Трек снят с публикации"}

    def delete_library_track(self, *, user_id: str, library_id: str) -> bool:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM user_library WHERE id = ? AND user_id = ?",
                (library_id, user_id),
            ).fetchone()
            if not row:
                raise ValueError("Трек не найден в фонотеке")
            conn.execute("DELETE FROM user_library WHERE id = ?", (library_id,))
        return True

    def get_published_library_item(self, library_id: str):
        with get_connection() as conn:
            return conn.execute(
                """
                SELECT ul.*, u.display_name, u.avatar_url
                FROM user_library ul
                LEFT JOIN users u ON u.id = ul.user_id
                WHERE ul.id = ? AND ul.published_at IS NOT NULL
                """,
                (library_id,),
            ).fetchone()

    def _sync_library_likes_count(self, conn, library_id: str) -> int:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM track_likes WHERE library_id = ?",
            (library_id,),
        ).fetchone()["c"]
        conn.execute(
            "UPDATE user_library SET likes = ? WHERE id = ?",
            (int(count), library_id),
        )
        return int(count)

    def like_published_track(self, *, user_id: str, library_id: str) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id FROM user_library
                WHERE id = ? AND published_at IS NOT NULL
                """,
                (library_id,),
            ).fetchone()
            if not row:
                raise ValueError("Публичный трек не найден")

            existing = conn.execute(
                """
                SELECT 1 FROM track_likes
                WHERE user_id = ? AND library_id = ?
                """,
                (user_id, library_id),
            ).fetchone()
            if existing:
                likes = self._sync_library_likes_count(conn, library_id)
                return {
                    "success": True,
                    "likes": likes,
                    "liked": True,
                    "already_liked": True,
                    "message": "Вы уже поставили лайк этому треку",
                }

            conn.execute(
                """
                INSERT INTO track_likes (user_id, library_id, created_at)
                VALUES (?, ?, ?)
                """,
                (user_id, library_id, utc_now()),
            )
            likes = self._sync_library_likes_count(conn, library_id)
        return {
            "success": True,
            "likes": likes,
            "liked": True,
            "already_liked": False,
            "message": "Лайк добавлен",
        }

    def unlike_published_track(self, *, user_id: str, library_id: str) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id FROM user_library
                WHERE id = ? AND published_at IS NOT NULL
                """,
                (library_id,),
            ).fetchone()
            if not row:
                raise ValueError("Публичный трек не найден")

            cur = conn.execute(
                """
                DELETE FROM track_likes
                WHERE user_id = ? AND library_id = ?
                """,
                (user_id, library_id),
            )
            likes = self._sync_library_likes_count(conn, library_id)
            removed = cur.rowcount > 0
        return {
            "success": True,
            "likes": likes,
            "liked": False,
            "already_liked": False,
            "message": "Лайк отменён" if removed else "Лайк не был поставлен",
        }

    def list_track_comments(self, *, library_id: str, limit: int = 50) -> dict:
        limit = max(1, min(limit, 100))
        with get_connection() as conn:
            published = conn.execute(
                """
                SELECT id FROM user_library
                WHERE id = ? AND published_at IS NOT NULL
                """,
                (library_id,),
            ).fetchone()
            if not published:
                raise ValueError("Публичный трек не найден")

            rows = conn.execute(
                f"""
                SELECT tc.id, tc.text, tc.created_at, u.display_name
                FROM track_comments tc
                LEFT JOIN users u ON u.id = tc.user_id
                WHERE tc.library_id = ?
                ORDER BY tc.created_at DESC
                LIMIT {limit}
                """,
                (library_id,),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM track_comments WHERE library_id = ?",
                (library_id,),
            ).fetchone()["c"]
        items = [
            {
                "id": r["id"],
                "text": r["text"],
                "author_name": (r["display_name"] or "").strip() or "Аноним",
                "created_at": r["created_at"],
            }
            for r in rows
        ]
        return {"items": items, "total": int(total)}

    def add_track_comment(
        self, *, user_id: str, library_id: str, text: str
    ) -> dict:
        body = (text or "").strip()
        if len(body) < 2:
            raise ValueError("Комментарий слишком короткий")
        if len(body) > 500:
            raise ValueError("Комментарий не длиннее 500 символов")

        with get_connection() as conn:
            published = conn.execute(
                """
                SELECT id FROM user_library
                WHERE id = ? AND published_at IS NOT NULL
                """,
                (library_id,),
            ).fetchone()
            if not published:
                raise ValueError("Публичный трек не найден")

            user = conn.execute(
                "SELECT display_name FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            comment_id = str(uuid.uuid4())
            now = utc_now()
            conn.execute(
                """
                INSERT INTO track_comments (id, library_id, user_id, text, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (comment_id, library_id, user_id, body, now),
            )
        return {
            "id": comment_id,
            "text": body,
            "author_name": (user["display_name"] or "").strip() or "Аноним",
            "created_at": now,
        }

    def list_explore(self, *, limit: int = 50, user_id: str | None = None) -> list[dict]:
        limit = max(1, min(limit, 100))
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    ul.*,
                    u.display_name,
                    u.avatar_url,
                    (
                        SELECT COUNT(*)
                        FROM track_likes tl
                        WHERE tl.library_id = ul.id
                    ) AS likes_count,
                    (
                        SELECT COUNT(*)
                        FROM track_comments tc
                        WHERE tc.library_id = ul.id
                    ) AS comment_count,
                    CASE
                        WHEN ? IS NOT NULL AND EXISTS (
                            SELECT 1 FROM track_likes tl2
                            WHERE tl2.library_id = ul.id AND tl2.user_id = ?
                        ) THEN 1
                        ELSE 0
                    END AS liked_by_me
                FROM user_library ul
                LEFT JOIN users u ON u.id = ul.user_id
                WHERE ul.published_at IS NOT NULL
                ORDER BY likes_count DESC, ul.published_at DESC
                LIMIT {limit}
                """,
                (user_id, user_id),
            ).fetchall()
        return [self._explore_item_from_row(r) for r in rows]

    def _explore_item_from_row(self, row) -> dict:
        author = (row["display_name"] or "").strip() or "Аноним"
        likes = row["likes_count"] if "likes_count" in row.keys() else row["likes"]
        liked = bool(row["liked_by_me"]) if "liked_by_me" in row.keys() else False
        comments = row["comment_count"] if "comment_count" in row.keys() else 0
        return {
            "id": row["id"],
            "title": row["title"] or "Без названия",
            "genre": row["genre"] or "",
            "image_url": row["image_url"] or "",
            "duration": row["duration"] or 0,
            "likes": int(likes or 0),
            "published_at": row["published_at"] or "",
            "author_name": author,
            "author_avatar_url": row["avatar_url"],
            "listen_url": f"/api/explore/{row['id']}/listen",
            "liked_by_me": liked,
            "comment_count": int(comments or 0),
        }

    def link_generation_to_user(self, *, production_id: str, user_id: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE generations SET user_id = ? WHERE id = ?",
                (user_id, production_id),
            )

    def link_guest_generations(self, *, guest_id: str, user_id: str) -> int:
        with get_connection() as conn:
            cur = conn.execute(
                """
                UPDATE generations
                SET user_id = ?, guest_id = NULL
                WHERE guest_id = ? AND (user_id IS NULL OR user_id = '')
                """,
                (user_id, guest_id),
            )
        return cur.rowcount

    def _save_generation_to_library(self, conn, *, gen, user_id: str) -> list[str]:
        plan = json.loads(gen["plan_json"] or "{}")
        genre = plan.get("genre", "")
        now = utc_now()
        labels = ["A", "B"]
        urls = [gen["music_url_a"], gen["music_url_b"]]
        images = [gen["image_url_a"], gen["image_url_b"]]
        durations = [gen["duration_a"], gen["duration_b"]]
        title = gen["title"] or "Без названия"
        saved_ids: list[str] = []

        for i in range(2):
            if not urls[i]:
                continue
            lib_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO user_library (
                    id, user_id, generation_id, title, variant, audio_url,
                    image_url, duration, lyrics, genre, purchased_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lib_id,
                    user_id,
                    gen["id"],
                    f"{title} (вариант {labels[i]})",
                    labels[i],
                    urls[i],
                    images[i],
                    durations[i],
                    gen["lyrics"],
                    genre,
                    now,
                ),
            )
            saved_ids.append(lib_id)
        return saved_ids

    def complete_prepaid_generation(self, generation_id: str) -> bool:
        """После успешной музыки: нота уже списана при старте — кладём в фонотеку."""
        with get_connection() as conn:
            gen = conn.execute(
                "SELECT * FROM generations WHERE id = ?",
                (generation_id,),
            ).fetchone()
            if not gen or not gen["user_id"] or not gen["note_charged"]:
                return False
            if gen["purchased"] or gen["status"] != "success":
                return False
            self._save_generation_to_library(conn, gen=gen, user_id=gen["user_id"])
            conn.execute(
                "UPDATE generations SET purchased = 1, showcase_eligible = 0 WHERE id = ?",
                (generation_id,),
            )
        return True

    def purchase_generation(self, *, user_id: str, generation_id: str) -> dict:
        with get_connection() as conn:
            user = conn.execute(
                "SELECT balance FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not user:
                raise ValueError("Пользователь не найден")

            gen = conn.execute(
                "SELECT * FROM generations WHERE id = ? AND user_id = ?",
                (generation_id, user_id),
            ).fetchone()
            if not gen:
                raise ValueError("Генерация не найдена")
            if gen["purchased"]:
                raise ValueError("Уже куплено")
            if gen["status"] != "success":
                raise ValueError("Генерация ещё не готова")

            charge_balance = not bool(gen["note_charged"])
            if charge_balance and user["balance"] < 1:
                raise ValueError("Недостаточно нот на балансе")

            saved_ids = self._save_generation_to_library(
                conn, gen=gen, user_id=user_id
            )
            if charge_balance:
                conn.execute(
                    "UPDATE users SET balance = balance - 1 WHERE id = ?",
                    (user_id,),
                )
            conn.execute(
                "UPDATE generations SET purchased = 1, showcase_eligible = 0 WHERE id = ?",
                (generation_id,),
            )

            new_balance = conn.execute(
                "SELECT balance FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()["balance"]

        return {
            "success": True,
            "generation_id": generation_id,
            "library_ids": saved_ids,
            "balance": new_balance,
        }

    def add_balance(self, user_id: str, amount: int) -> int:
        with get_connection() as conn:
            conn.execute(
                "UPDATE users SET balance = balance + ? WHERE id = ?",
                (amount, user_id),
            )
            row = conn.execute(
                "SELECT balance FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return int(row["balance"])