"""Запас ApiPass, если sunoapi уже взял задачу и сломался."""

import uuid

from backend import settings as sf_settings
from backend.database.db import get_connection, init_db
from backend.services.history import HistoryService
from backend.services.music_poll_service import MusicPollService


def _insert_suno_job(*, production_id: str, task_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO generations (
                id, task_id, created_at, title, lyrics, style, plan_json,
                status, music_provider, music_fallback
            ) VALUES (?, ?, datetime('now'), ?, ?, ?, ?, 'generating', 'sunoapi', 0)
            """,
            (
                production_id,
                task_id,
                "Тест",
                "[Verse 1]\nстрока",
                "pop",
                "{}",
            ),
        )


def test_suno_task_fail_starts_apipass_once(monkeypatch):
    init_db()
    monkeypatch.setattr(sf_settings, "MUSIC_PROVIDER", "fallback_suno")
    monkeypatch.setattr(sf_settings, "APIPASS_API_KEY", "test-key")
    production_id = str(uuid.uuid4())
    suno_task = f"suno-{uuid.uuid4()}"
    _insert_suno_job(production_id=production_id, task_id=suno_task)

    created: dict = {}
    poll = MusicPollService()
    poll._music.get_status = lambda task_id, provider=None: {
        "state": "failed",
        "fail_code": "402",
        "fail_msg": "insufficient credits",
    }

    def create_on(provider, **kwargs):
        created["provider"] = provider
        created["title"] = kwargs.get("title")
        return "apipass-reserve-1"

    poll._music.create_on = create_on
    poll._queue.remove_poll = lambda **k: None
    poll._queue.enqueue_poll = lambda **k: created.setdefault("enqueued", k["task_id"])

    assert poll.process_task(suno_task) == "pending"
    assert created["provider"] == "apipass"
    assert created["enqueued"] == "apipass-reserve-1"

    history = HistoryService()
    row = history.get_by_id(production_id)
    assert row["task_id"] == "apipass-reserve-1"
    assert row["music_provider"] == "apipass"
    assert row["prior_task_id"] == suno_task
    assert row["status"] == "generating"
    assert history.get_by_task(suno_task)["id"] == production_id

    created.clear()
    poll._music.get_status = lambda task_id, provider=None: {
        "state": "failed",
        "fail_msg": "apipass also failed",
    }
    assert poll.process_task("apipass-reserve-1") == "failed"
    assert "provider" not in created
    row = history.get_by_id(production_id)
    assert row["status"] == "failed"

    with get_connection() as conn:
        conn.execute("DELETE FROM generations WHERE id = ?", (production_id,))


def test_no_handoff_when_already_on_apipass(monkeypatch):
    init_db()
    monkeypatch.setattr(sf_settings, "MUSIC_PROVIDER", "fallback_suno")
    monkeypatch.setattr(sf_settings, "APIPASS_API_KEY", "test-key")
    production_id = str(uuid.uuid4())
    task_id = f"apipass-{uuid.uuid4()}"
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO generations (
                id, task_id, created_at, title, lyrics, style, plan_json,
                status, music_provider, music_fallback
            ) VALUES (?, ?, datetime('now'), 'Т', '', 'pop', '{}', 'generating', 'apipass', 0)
            """,
            (production_id, task_id),
        )

    poll = MusicPollService()
    poll._music.create_on = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("запас не должен вызываться")
    )
    poll._music.get_status = lambda task_id, provider=None: {
        "state": "failed",
        "fail_msg": "down",
    }
    poll._queue.remove_poll = lambda **k: None
    assert poll.process_task(task_id) == "failed"

    with get_connection() as conn:
        conn.execute("DELETE FROM generations WHERE id = ?", (production_id,))


def test_claim_music_fallback_only_once():
    init_db()
    production_id = str(uuid.uuid4())
    _insert_suno_job(production_id=production_id, task_id="suno-once")
    history = HistoryService()
    assert history.claim_music_fallback(production_id) is True
    assert history.claim_music_fallback(production_id) is False
    with get_connection() as conn:
        conn.execute("DELETE FROM generations WHERE id = ?", (production_id,))
