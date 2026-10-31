"""Неудачная копия повторяется с паузой и не долбит цех без конца."""

from backend.database.db import get_connection, init_db, utc_now
from backend.services.cabinet_service import CabinetService
from backend.services.storage_service import MAX_COPY_ATTEMPTS, StorageService


def _insert_song(song_id: str, url: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO generations (
                id, title, status, music_url_a, created_at, purchased, storage_synced
            ) VALUES (?, 'Копия', 'success', ?, ?, 0, 0)
            """,
            (song_id, url, utc_now()),
        )


def _forget(song_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM user_library WHERE generation_id = ?", (song_id,))
        conn.execute("DELETE FROM generations WHERE id = ?", (song_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (song_id,))


def test_failed_copy_waits_and_then_stops(monkeypatch):
    init_db()
    song_id = "copy-retry-song"
    _forget(song_id)
    _insert_song(song_id, "https://cdn.example/live.mp3")
    calls: list[str] = []

    def _fail(self, production_id, force=False):
        calls.append(production_id)
        return False

    monkeypatch.setattr(StorageService, "enabled", lambda self: True)
    monkeypatch.setattr(StorageService, "mirror_generation", _fail)
    storage = StorageService()
    try:
        assert storage.copy_generation(song_id) is False
        assert calls == [song_id]
        with get_connection() as conn:
            row = conn.execute(
                "SELECT storage_attempts, storage_next_try FROM generations WHERE id = ?",
                (song_id,),
            ).fetchone()
        assert int(row["storage_attempts"]) == 1
        assert row["storage_next_try"]

        assert storage.copy_generation(song_id, respect_schedule=True) is False
        assert calls == [song_id]

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE generations
                SET storage_next_try = '2000-01-01T00:00:00+00:00'
                WHERE id = ?
                """,
                (song_id,),
            )
        assert storage.copy_generation(song_id, respect_schedule=True) is False
        assert calls == [song_id, song_id]

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE generations
                SET storage_attempts = ?, storage_next_try = NULL
                WHERE id = ?
                """,
                (MAX_COPY_ATTEMPTS, song_id),
            )
        assert storage.copy_generation(song_id) is False
        assert calls == [song_id, song_id]
    finally:
        _forget(song_id)


def test_due_copy_is_saved_once(monkeypatch):
    init_db()
    song_id = "copy-retry-ok"
    _forget(song_id)
    _insert_song(song_id, "https://cdn.example/ok.mp3")

    def _ok(self, production_id, force=False):
        with get_connection() as conn:
            conn.execute(
                "UPDATE generations SET storage_synced = 1 WHERE id = ?",
                (production_id,),
            )
        return True

    monkeypatch.setattr(StorageService, "enabled", lambda self: True)
    monkeypatch.setattr(StorageService, "mirror_generation", _ok)
    storage = StorageService()
    try:
        assert storage.copy_generation(song_id) is True
        assert storage.copy_generation(song_id) is True
        with get_connection() as conn:
            synced = conn.execute(
                "SELECT storage_synced FROM generations WHERE id = ?",
                (song_id,),
            ).fetchone()["storage_synced"]
        assert int(synced) == 1
    finally:
        _forget(song_id)


def test_purchase_takes_the_copied_address(monkeypatch):
    init_db()
    user_id = "copy-buyer"
    song_id = "copy-buy-song"
    _forget(song_id)
    _forget(user_id)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, balance, created_at)
            VALUES (?, ?, 'Покупатель', 2, ?)
            """,
            (user_id, f"{user_id}@demo.local", utc_now()),
        )
    _insert_song(song_id, "https://cdn.example/before.mp3")
    with get_connection() as conn:
        conn.execute(
            "UPDATE generations SET user_id = ? WHERE id = ?",
            (user_id, song_id),
        )

    copied = "https://music.s3.regru.cloud/tracks/copy-buy-song/a.mp3"

    def _copy(self, production_id, respect_schedule=False):
        with get_connection() as conn:
            conn.execute(
                "UPDATE generations SET music_url_a = ? WHERE id = ?",
                (copied, production_id),
            )
        return True

    monkeypatch.setattr(StorageService, "copy_generation", _copy)
    try:
        CabinetService().purchase_generation(user_id=user_id, generation_id=song_id)
        with get_connection() as conn:
            audio = conn.execute(
                "SELECT audio_url FROM user_library WHERE generation_id = ?",
                (song_id,),
            ).fetchone()["audio_url"]
        assert audio == copied
    finally:
        _forget(song_id)
        _forget(user_id)
