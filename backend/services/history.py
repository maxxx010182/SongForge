import json

from backend.database.db import dumps_json, get_connection, init_db, utc_now
from backend.models import ProductionPlan, TrackVariant


class HistoryService:
    def __init__(self) -> None:
        init_db()

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
        with get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO generations (
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
                    dumps_json(plan.model_dump()),
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
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO generations (
                    id, task_id, created_at, idea, title, lyrics, style,
                    plan_json, status, user_id, guest_id
                ) VALUES (
                    ?, ?, COALESCE(
                        (SELECT created_at FROM generations WHERE id = ?),
                        ?
                    ), ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    production_id,
                    task_id,
                    production_id,
                    utc_now(),
                    idea,
                    title,
                    lyrics,
                    style,
                    dumps_json(plan.model_dump()),
                    "generating",
                    user_id,
                    guest_id,
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

    def update_task_result(
        self,
        *,
        task_id: str,
        status: str,
        tracks: list[TrackVariant],
        fail_code: str = "",
        fail_msg: str = "",
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
                    fail_msg = ?
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
                    task_id,
                ),
            )