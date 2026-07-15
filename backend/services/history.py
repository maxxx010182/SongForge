import json

from backend.database.db import dumps_json, get_connection, init_db, utc_now
from backend.models import ProductionPlan, TrackVariant


class HistoryService:
    def __init__(self) -> None:
        init_db()

    @staticmethod
    def _generation_exists(conn, production_id: str) -> bool:
        row = conn.execute(
            "SELECT id FROM generations WHERE id = ?",
            (production_id,),
        ).fetchone()
        return row is not None

    def save_production(
        self,
        *,
        production_id: str,
        idea: str,
        optimized_idea: str,
        plan: ProductionPlan,
        title: str,
        lyrics: str,
        style: str,
        user_id: str | None = None,
        guest_id: str | None = None,
    ) -> None:
        plan_json = dumps_json(plan.model_dump())
        with get_connection() as conn:
            if self._generation_exists(conn, production_id):
                conn.execute(
                    """
                    UPDATE generations SET
                        idea = ?,
                        optimized_idea = ?,
                        title = ?,
                        lyrics = ?,
                        style = ?,
                        plan_json = ?,
                        status = ?,
                        user_id = COALESCE(?, user_id),
                        guest_id = COALESCE(?, guest_id)
                    WHERE id = ?
                    """,
                    (
                        idea,
                        optimized_idea,
                        title,
                        lyrics,
                        style,
                        plan_json,
                        "planned",
                        user_id,
                        guest_id,
                        production_id,
                    ),
                )
                return

            conn.execute(
                """
                INSERT INTO generations (
                    id, created_at, idea, optimized_idea, title, lyrics, style,
                    plan_json, status, user_id, guest_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    production_id,
                    utc_now(),
                    idea,
                    optimized_idea,
                    title,
                    lyrics,
                    style,
                    plan_json,
                    "planned",
                    user_id,
                    guest_id,
                ),
            )

    def attach_task(
        self,
        *,
        production_id: str,
        task_id: str,
        idea: str,
        title: str,
        lyrics: str,
        style: str,
        plan: ProductionPlan,
        user_id: str | None = None,
        guest_id: str | None = None,
        music_provider: str = "apipass",
    ) -> None:
        plan_json = dumps_json(plan.model_dump())
        with get_connection() as conn:
            if self._generation_exists(conn, production_id):
                conn.execute(
                    """
                    UPDATE generations SET
                        task_id = ?,
                        idea = ?,
                        title = ?,
                        lyrics = ?,
                        style = ?,
                        plan_json = ?,
                        status = ?,
                        music_url_a = NULL,
                        music_url_b = NULL,
                        image_url_a = NULL,
                        image_url_b = NULL,
                        duration_a = NULL,
                        duration_b = NULL,
                        fail_code = NULL,
                        fail_msg = NULL,
                        storage_synced = 0,
                        music_provider = ?,
                        user_id = COALESCE(?, user_id),
                        guest_id = COALESCE(?, guest_id)
                    WHERE id = ?
                    """,
                    (
                        task_id,
                        idea,
                        title,
                        lyrics,
                        style,
                        plan_json,
                        "generating",
                        music_provider,
                        user_id,
                        guest_id,
                        production_id,
                    ),
                )
                return

            conn.execute(
                """
                INSERT INTO generations (
                    id, task_id, created_at, idea, title, lyrics, style,
                    plan_json, status, user_id, guest_id, music_provider
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    production_id,
                    task_id,
                    utc_now(),
                    idea,
                    title,
                    lyrics,
                    style,
                    plan_json,
                    "generating",
                    user_id,
                    guest_id,
                    music_provider,
                ),
            )

    def get_production(self, production_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM generations WHERE id = ?",
                (production_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "idea": row["idea"],
            "title": row["title"],
            "lyrics": row["lyrics"],
            "style": row["style"],
            "plan": json.loads(row["plan_json"] or "{}"),
            "status": row["status"],
        }

    def get_by_task(self, task_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM generations WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def get_by_id(self, production_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM generations WHERE id = ?",
                (production_id,),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def update_progress(self, *, task_id: str, progress_hint: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE generations SET progress_hint = ? WHERE task_id = ?",
                (progress_hint, task_id),
            )

    def list_generating_tasks(self) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, task_id, music_provider
                FROM generations
                WHERE status = 'generating' AND task_id IS NOT NULL AND task_id != ''
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def count_generating(self) -> int:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM generations
                WHERE status = 'generating'
                """
            ).fetchone()
        return int(row["c"]) if row else 0

    def count_generating_for_user(self, user_id: str) -> int:
        if not (user_id or "").strip():
            return 0
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM generations
                WHERE status = 'generating' AND user_id = ?
                """,
                (user_id,),
            ).fetchone()
        return int(row["c"]) if row else 0

    def update_task_result(
        self,
        *,
        task_id: str,
        status: str,
        tracks: list[TrackVariant],
        fail_code: str = "",
        fail_msg: str = "",
        progress_hint: str = "",
    ) -> None:
        track_a = tracks[0] if len(tracks) > 0 else None
        track_b = tracks[1] if len(tracks) > 1 else None

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE generations SET
                    status = ?,
                    music_url_a = ?,
                    music_url_b = ?,
                    image_url_a = ?,
                    image_url_b = ?,
                    duration_a = ?,
                    duration_b = ?,
                    fail_code = ?,
                    fail_msg = ?,
                    progress_hint = COALESCE(NULLIF(?, ''), progress_hint)
                WHERE task_id = ?
                """,
                (
                    status,
                    track_a.audio_url if track_a else None,
                    track_b.audio_url if track_b else None,
                    track_a.image_url if track_a else None,
                    track_b.image_url if track_b else None,
                    track_a.duration if track_a else None,
                    track_b.duration if track_b else None,
                    fail_code,
                    fail_msg,
                    progress_hint,
                    task_id,
                ),
            )

    def update_music_urls(
        self,
        *,
        production_id: str,
        music_url_a: str | None = None,
        music_url_b: str | None = None,
        storage_synced: bool | None = None,
    ) -> None:
        with get_connection() as conn:
            if music_url_a is not None:
                conn.execute(
                    "UPDATE generations SET music_url_a = ? WHERE id = ?",
                    (music_url_a, production_id),
                )
            if music_url_b is not None:
                conn.execute(
                    "UPDATE generations SET music_url_b = ? WHERE id = ?",
                    (music_url_b, production_id),
                )
            if storage_synced is not None:
                conn.execute(
                    "UPDATE generations SET storage_synced = ? WHERE id = ?",
                    (1 if storage_synced else 0, production_id),
                )