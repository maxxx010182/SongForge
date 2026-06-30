import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.settings import DATA_DIR, DB_PATH


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS generations (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                created_at TEXT NOT NULL,
                idea TEXT,
                optimized_idea TEXT,
                title TEXT,
                lyrics TEXT,
                style TEXT,
                plan_json TEXT,
                status TEXT NOT NULL,
                music_url_a TEXT,
                music_url_b TEXT,
                image_url_a TEXT,
                image_url_b TEXT,
                duration_a REAL,
                duration_b REAL,
                fail_code TEXT,
                fail_msg TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_generations_task_id ON generations(task_id)"
        )


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dumps_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)