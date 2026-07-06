"""Тесты v2.10: WAL, атомарные ноты, очередь, storage."""

import sqlite3
import uuid

from backend.database.db import DB_PATH, get_connection, init_db
from backend.services.generation_quota_service import GenerationQuotaService
from backend.services.job_queue import JobQueue
from backend.services.storage_service import StorageService
from backend.settings import SQLITE_TIMEOUT_SEC


def test_sqlite_wal_and_timeout():
    init_db()
    with get_connection() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        timeout_ms = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert str(mode).lower() == "wal"
    assert int(timeout_ms) >= int(SQLITE_TIMEOUT_SEC * 1000)


def test_atomic_balance_deduction():
    init_db()
    user_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, balance, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (user_id, "atomic@test.local", "atomic_user", 1),
        )

    quota = GenerationQuotaService()
    user = {"id": user_id, "balance": 1}
    quota.consume_on_start(mode="paid", user=user, guest_id="guest-test")

    with get_connection() as conn:
        balance = conn.execute(
            "SELECT balance FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()["balance"]
    assert balance == 0

    try:
        quota.consume_on_start(mode="paid", user=user, guest_id="guest-test")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_job_queue_enqueue_without_redis():
    queue = JobQueue()
    queue.enqueue_poll(task_id="task-test-1", production_id="prod-1")
    assert isinstance(queue.ping(), bool)


def test_storage_disabled_by_default():
    storage = StorageService()
    assert storage.enabled() is False
    assert storage.mirror_generation("missing-id") is False


def test_db_has_progress_hint_column():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(generations)")}
    conn.close()
    assert "progress_hint" in cols
    assert "storage_synced" in cols