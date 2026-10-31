"""Купленные файлы со ссылки цеха переключаются на наше хранилище."""

import importlib.util
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fix-phonotheque-copies.py"
spec = importlib.util.spec_from_file_location("fix_phonotheque_copies", SCRIPT)
fix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fix)

HOST = "music.s3.regru.cloud"


class FakeStore:
    def __init__(self, have: set[str] | None = None, accept: set[str] | None = None):
        self.have = set(have or [])
        self.accept = set(accept or [])
        self.saved: list[str] = []

    def public_url(self, key: str) -> str:
        return f"https://{HOST}/{key}"

    def exists(self, key: str) -> bool | None:
        return key in self.have

    def save_from_url(self, key: str, source_url: str) -> bool:
        if source_url not in self.accept:
            return False
        self.saved.append(key)
        self.have.add(key)
        return True


def build_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE users (id TEXT, is_persona INTEGER);
        CREATE TABLE generations (
            id TEXT, status TEXT, purchased INTEGER, note_charged INTEGER,
            storage_synced INTEGER, music_url_a TEXT, music_url_b TEXT
        );
        CREATE TABLE user_library (
            id TEXT, user_id TEXT, generation_id TEXT, variant TEXT, audio_url TEXT
        );
        INSERT INTO users VALUES ('u1', 0), ('p1', 1);
        INSERT INTO generations VALUES
          ('g1', 'success', 1, 1, 1,
           'https://music.s3.regru.cloud/tracks/g1/a.mp3',
           'https://music.s3.regru.cloud/tracks/g1/b.mp3'),
          ('g2', 'success', 1, 1, 0,
           'https://cdn.example/g2a.mp3',
           'https://cdn.example/g2b.mp3'),
          ('g3', 'success', 1, 1, 0,
           'https://cdn.example/dead.mp3',
           ''),
          ('g4', 'success', 0, 0, 0,
           'https://cdn.example/demo.mp3',
           '');
        INSERT INTO user_library VALUES
          ('l1', 'u1', 'g1', 'A', 'https://cdn.example/old-a.mp3'),
          ('l2', 'u1', 'g1', 'B', 'https://music.s3.regru.cloud/tracks/g1/b.mp3'),
          ('l3', 'u1', 'g2', 'A', 'https://cdn.example/g2a.mp3'),
          ('l4', 'u1', 'g2', 'B', 'https://cdn.example/g2b.mp3'),
          ('l5', 'u1', 'g3', 'A', 'https://cdn.example/dead.mp3'),
          ('l6', 'p1', 'g4', 'A', 'https://cdn.example/demo.mp3');
        """
    )
    conn.commit()
    conn.close()


def urls(path: Path) -> dict[str, str]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    found = {
        row["id"]: row["audio_url"]
        for row in conn.execute("SELECT id, audio_url FROM user_library")
    }
    conn.close()
    return found


def test_relink_keeps_dead_link_and_skips_unsold(tmp_path):
    db = tmp_path / "songforge.db"
    build_db(db)
    store = FakeStore(
        have={"tracks/g1/a.mp3"},
        accept={"https://cdn.example/g2a.mp3", "https://cdn.example/g2b.mp3"},
    )
    result = fix.repair(db, HOST, store)
    found = urls(db)
    assert result == {"switched": 1, "fetched": 2, "failed": 1, "unchecked": 0}
    assert found["l1"] == "https://music.s3.regru.cloud/tracks/g1/a.mp3"
    assert found["l2"].endswith("/tracks/g1/b.mp3")
    assert found["l3"] == "https://music.s3.regru.cloud/tracks/g2/a.mp3"
    assert found["l4"] == "https://music.s3.regru.cloud/tracks/g2/b.mp3"
    assert found["l5"] == "https://cdn.example/dead.mp3"
    assert found["l6"] == "https://cdn.example/demo.mp3"
    assert store.saved == ["tracks/g2/a.mp3", "tracks/g2/b.mp3"]

    conn = sqlite3.connect(db)
    flags = dict(conn.execute("SELECT id, storage_synced FROM generations"))
    conn.close()
    assert flags["g1"] == 1
    assert flags["g2"] == 1
    assert flags["g3"] == 0


def test_short_or_foreign_body_is_not_audio():
    assert fix.looks_like_audio(b"ID3" + b"\x00" * 100_000)
    assert not fix.looks_like_audio(b'{"ok":false}')
    assert not fix.looks_like_audio(b"ID3" + b"\x00" * 20)
