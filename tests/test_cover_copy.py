"""Обложка уходит в наше хранилище. Мёртвый адрес не трогает музыку."""

from backend.database.db import get_connection, init_db, utc_now
from backend.models import TrackVariant
from backend.services.cabinet_service import CabinetService
from backend.services.history import HistoryService
from backend.services.storage_service import StorageService, image_kind

OUR = "https://songforge-music.s3.regru.cloud/tracks/cover-song/a-cover.jpg"


def _forget(song_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM user_library WHERE generation_id = ?", (song_id,))
        conn.execute("DELETE FROM generations WHERE id = ?", (song_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (song_id,))


def _song(song_id: str, image_a: str, image_b: str = "") -> None:
    _forget(song_id)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, balance, created_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            (song_id, f"{song_id}@demo.local", song_id, utc_now()),
        )
        conn.execute(
            """
            INSERT INTO generations (
                id, title, status, music_url_a, image_url_a, image_url_b,
                created_at, user_id, purchased, storage_synced
            ) VALUES (?, 'Обложка', 'success', ?, ?, ?, ?, ?, 1, 1)
            """,
            (
                song_id,
                "https://songforge-music.s3.regru.cloud/tracks/x/a.mp3",
                image_a,
                image_b,
                utc_now(),
                song_id,
            ),
        )
        conn.execute(
            """
            INSERT INTO user_library (
                id, user_id, generation_id, title, variant, audio_url,
                image_url, purchased_at
            ) VALUES (?, ?, ?, 'Обложка', 'A', ?, ?, ?)
            """,
            (
                song_id + "-lib",
                song_id,
                song_id,
                "https://songforge-music.s3.regru.cloud/tracks/x/a.mp3",
                image_a,
                utc_now(),
            ),
        )


def test_image_kind_rejects_html():
    assert image_kind(b"\xff\xd8\xff\x00") == ("image/jpeg", "jpg")
    assert image_kind(b"<html>no</html>") is None


def test_live_cover_is_stored_on_our_host(monkeypatch):
    init_db()
    song_id = "cover-live"
    _song(song_id, "https://cdn.example/cover.jpg")
    calls: list[str] = []

    def _upload(self, *, key_prefix: str, source_url: str) -> str:
        calls.append(source_url)
        return OUR

    monkeypatch.setattr(StorageService, "enabled", lambda self: True)
    monkeypatch.setattr(StorageService, "upload_image_from_url", _upload)
    try:
        result = StorageService().copy_covers(song_id)
        assert result.state == "ready"
        assert result.saved == 1
        assert calls == ["https://cdn.example/cover.jpg"]
        with get_connection() as conn:
            row = conn.execute(
                "SELECT image_url_a, cover_synced, storage_synced FROM generations WHERE id = ?",
                (song_id,),
            ).fetchone()
            lib = conn.execute(
                "SELECT image_url FROM user_library WHERE generation_id = ?",
                (song_id,),
            ).fetchone()
        assert row["image_url_a"] == OUR
        assert int(row["cover_synced"]) == 1
        assert int(row["storage_synced"]) == 1
        assert lib["image_url"] == OUR
        again = StorageService().copy_covers(song_id)
        assert again.saved == 0
        assert calls == ["https://cdn.example/cover.jpg"]
    finally:
        _forget(song_id)


def test_dead_cover_stays_when_copy_fails(monkeypatch):
    init_db()
    song_id = "cover-dead"
    _song(song_id, "https://musicfile.removeai.ai/gone.jpeg")

    def _fail(self, *, key_prefix: str, source_url: str) -> str:
        raise RuntimeError("silent")

    monkeypatch.setattr(StorageService, "enabled", lambda self: True)
    monkeypatch.setattr(StorageService, "upload_image_from_url", _fail)
    storage = StorageService()
    try:
        first = storage.copy_covers(song_id)
        assert first.state == "failed"
        assert first.saved == 0
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT image_url_a, cover_synced, cover_attempts, storage_synced
                FROM generations WHERE id = ?
                """,
                (song_id,),
            ).fetchone()
        assert row["image_url_a"] == "https://musicfile.removeai.ai/gone.jpeg"
        assert int(row["cover_synced"]) == 0
        assert int(row["cover_attempts"]) == 1
        assert int(row["storage_synced"]) == 1

        for _ in range(8):
            again = storage.copy_covers(song_id, give_up=True)
            assert again.state == "failed"
            assert again.cleared == 0
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT image_url_a, cover_synced, cover_attempts
                FROM generations WHERE id = ?
                """,
                (song_id,),
            ).fetchone()
            lib = conn.execute(
                "SELECT image_url FROM user_library WHERE generation_id = ?",
                (song_id,),
            ).fetchone()
        assert row["image_url_a"] == "https://musicfile.removeai.ai/gone.jpeg"
        assert int(row["cover_synced"]) == 0
        assert int(row["cover_attempts"]) == 9
        assert lib["image_url"] == "https://musicfile.removeai.ai/gone.jpeg"
    finally:
        _forget(song_id)


def test_saved_cover_is_not_replaced():
    init_db()
    song_id = "cover-keep"
    factory = "https://musicfile.removeai.ai/later.jpeg"
    _song(song_id, OUR)
    with get_connection() as conn:
        conn.execute(
            "UPDATE generations SET task_id = ? WHERE id = ?",
            (song_id + "-task", song_id),
        )
    try:
        HistoryService().update_task_result(
            task_id=song_id + "-task",
            status="success",
            tracks=[
                TrackVariant(
                    audio_url="https://cdn.example/a.mp3",
                    image_url=factory,
                )
            ],
        )
        with get_connection() as conn:
            row = conn.execute(
                "SELECT image_url_a, image_url_b FROM generations WHERE id = ?",
                (song_id,),
            ).fetchone()
        assert row["image_url_a"] == OUR

        HistoryService().update_task_result(
            task_id=song_id + "-task",
            status="success",
            tracks=[TrackVariant(audio_url="https://cdn.example/a.mp3", image_url="")],
        )
        with get_connection() as conn:
            conn.execute(
                "UPDATE generations SET image_url_a = ? WHERE id = ?",
                (factory, song_id),
            )
        HistoryService().update_task_result(
            task_id=song_id + "-task",
            status="success",
            tracks=[TrackVariant(audio_url="https://cdn.example/a.mp3", image_url="")],
        )
        with get_connection() as conn:
            row = conn.execute(
                "SELECT image_url_a FROM generations WHERE id = ?",
                (song_id,),
            ).fetchone()
            conn.execute(
                "UPDATE generations SET image_url_a = ? WHERE id = ?",
                (factory, song_id),
            )
        assert row["image_url_a"] == factory

        CabinetService().sync_library_audio_from_generation(song_id)
        with get_connection() as conn:
            lib = conn.execute(
                "SELECT image_url FROM user_library WHERE generation_id = ?",
                (song_id,),
            ).fetchone()
        assert lib["image_url"] == OUR
    finally:
        _forget(song_id)


def test_retry_still_takes_foreign_cover_marked_done(monkeypatch):
    init_db()
    old_id = "cover-old-foreign"
    new_id = "cover-new-ours"
    factory = "https://cdn.example/old-cover.jpg"
    calls: list[str] = []

    def _upload(self, *, key_prefix: str, source_url: str) -> str:
        calls.append(source_url)
        return OUR

    monkeypatch.setattr(StorageService, "enabled", lambda self: True)
    monkeypatch.setattr(StorageService, "upload_image_from_url", _upload)
    try:
        _song(old_id, factory)
        _song(new_id, OUR)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE generations
                SET created_at = ?, cover_synced = 1
                WHERE id = ?
                """,
                ("2020-01-01T00:00:00+00:00", old_id),
            )
            conn.execute(
                "UPDATE generations SET created_at = ? WHERE id = ?",
                ("2026-11-08T00:00:00+00:00", new_id),
            )
        saved = StorageService().retry_pending_covers(limit=2)
        assert saved == 1
        assert calls == [factory]
    finally:
        _forget(old_id)
        _forget(new_id)


def test_our_cover_is_not_downloaded_again(monkeypatch):
    init_db()
    song_id = "cover-ours"
    _song(song_id, OUR)
    calls: list[str] = []

    def _upload(self, *, key_prefix: str, source_url: str) -> str:
        calls.append(source_url)
        return source_url

    monkeypatch.setattr(StorageService, "enabled", lambda self: True)
    monkeypatch.setattr(StorageService, "upload_image_from_url", _upload)
    try:
        result = StorageService().copy_covers(song_id)
        assert result.state == "ready"
        assert result.already == 1
        assert result.saved == 0
        assert calls == []
    finally:
        _forget(song_id)
