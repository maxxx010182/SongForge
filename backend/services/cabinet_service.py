import json
import uuid

from backend.database.db import get_connection, init_db, utc_now


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

        url = row["music_url_b"] if variant_key == "b" else row["music_url_a"]
        if not url:
            raise ValueError("Аудио не найдено")

        image_url = (
            row["image_url_b"] if variant_key == "b" else row["image_url_a"]
        ) or row["image_url_a"] or row["image_url_b"]

        return {
            "audio_url": url,
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
            }
            for r in rows
        ]

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

    def purchase_generation(self, *, user_id: str, generation_id: str) -> dict:
        with get_connection() as conn:
            user = conn.execute(
                "SELECT balance FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not user:
                raise ValueError("Пользователь не найден")
            if user["balance"] < 1:
                raise ValueError("Недостаточно нот на балансе")

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
                        generation_id,
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