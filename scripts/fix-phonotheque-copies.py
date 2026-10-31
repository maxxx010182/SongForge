#!/usr/bin/env python3
"""Забрать в наше хранилище купленные файлы, которые ещё смотрят на ссылку цеха.

Меняет только эти адреса в фонотеке. Ничего не удаляет. Ссылки и названия не печатает.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path("/root/SongForge")
if ROOT.is_dir() and str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB = Path(os.environ.get("SONGFORGE_DB", "/root/SongForge/data/songforge.db"))
ENV = Path(os.environ.get("SONGFORGE_ENV", "/root/SongForge/.env"))
MIN_AUDIO_BYTES = 100_000
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

PHONO_SQL = """
    SELECT ul.id AS library_id,
           ul.variant AS variant,
           ul.audio_url AS audio_url,
           g.id AS generation_id,
           g.music_url_a AS music_url_a,
           g.music_url_b AS music_url_b,
           COALESCE(g.storage_synced, 0) AS storage_synced
    FROM user_library ul
    LEFT JOIN users u ON u.id = ul.user_id
    JOIN generations g ON g.id = ul.generation_id
    WHERE COALESCE(u.is_persona, 0) = 0
      AND (
        COALESCE(g.purchased, 0) = 1
        OR COALESCE(g.note_charged, 0) = 1
      )
"""


def public_host(env_path: Path) -> str:
    if not env_path.is_file():
        return ""
    base = ""
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, val = text.split("=", 1)
        if key.strip() == "S3_PUBLIC_BASE":
            base = val.strip().strip('"').strip("'")
    return (urlparse(base).netloc or "").lower()


def on_our_storage(url: str, host: str) -> bool:
    raw = (url or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw)
    netloc = (parsed.netloc or "").lower()
    path = parsed.path or ""
    if host and netloc == host:
        return True
    return "s3.regru.cloud" in netloc and "/tracks/" in path and path.endswith(".mp3")


def file_letter(variant: str) -> str:
    token = (variant or "").strip().upper()
    if token.startswith("B") or token == "1":
        return "b"
    return "a"


def looks_like_audio(data: bytes) -> bool:
    if len(data) < MIN_AUDIO_BYTES:
        return False
    if data[:3] == b"ID3":
        return True
    return len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0


class LiveStore:
    def __init__(self) -> None:
        from backend.services.storage_service import StorageService

        self.storage = StorageService()
        self.client = None

    def enabled(self) -> bool:
        return self.storage.enabled()

    def public_url(self, key: str) -> str:
        return self.storage.public_url(key)

    def _client(self):
        if self.client is None:
            self.client = self.storage._get_client()
        return self.client

    def exists(self, key: str) -> bool | None:
        from botocore.exceptions import ClientError

        try:
            self._client().head_object(Bucket=self._bucket(), Key=key)
            return True
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status in {403, 404} or code in {"403", "404", "NoSuchKey", "NotFound"}:
                return False
            return None
        except Exception:
            return None

    def save_from_url(self, key: str, source_url: str) -> bool:
        import requests

        try:
            response = requests.get(
                source_url,
                timeout=120,
                headers={"User-Agent": UA, "Accept": "audio/*,*/*"},
            )
            response.raise_for_status()
            data = response.content
            if not looks_like_audio(data):
                return False
            self._client().put_object(
                Bucket=self._bucket(),
                Key=key,
                Body=data,
                ContentType="audio/mpeg",
            )
            return True
        except Exception:
            return False

    def _bucket(self) -> str:
        from backend.settings import S3_BUCKET

        return S3_BUCKET


def connect(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def load_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute(PHONO_SQL))


def _generation_url(row: sqlite3.Row, letter: str) -> str:
    return (row["music_url_b"] if letter == "b" else row["music_url_a"]) or ""


def repair(db: Path, host: str, store) -> dict[str, int]:
    conn = connect(db)
    try:
        rows = load_rows(conn)
    finally:
        conn.close()

    groups: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in rows:
        if on_our_storage(row["audio_url"], host):
            continue
        letter = file_letter(row["variant"])
        groups.setdefault((row["generation_id"], letter), []).append(row)

    switched = 0
    fetched = 0
    failed = 0
    unchecked = 0
    touched: set[str] = set()

    for (generation_id, letter), group in groups.items():
        key = f"tracks/{generation_id}/{letter}.mp3"
        sample = group[0]
        gen_url = _generation_url(sample, letter)
        new_url = ""
        kind = ""
        if on_our_storage(gen_url, host) and store.exists(key) is True:
            new_url = gen_url.strip()
            kind = "switched"
        elif store.exists(key) is True:
            new_url = store.public_url(key)
            kind = "switched"
        elif store.exists(key) is None and on_our_storage(gen_url, host):
            kind = "unchecked"
        else:
            sources: list[str] = []
            for candidate in (sample["audio_url"] or "", gen_url):
                text = candidate.strip()
                if text and text not in sources and not on_our_storage(text, host):
                    sources.append(text)
            for source in sources:
                if store.save_from_url(key, source):
                    new_url = store.public_url(key)
                    kind = "fetched"
                    break
            if not new_url:
                kind = "failed"

        if not new_url:
            if kind == "unchecked":
                unchecked += len(group)
            else:
                failed += len(group)
            continue

        conn = connect(db)
        try:
            for row in group:
                if (row["audio_url"] or "").strip() == new_url:
                    continue
                conn.execute(
                    "UPDATE user_library SET audio_url = ? WHERE id = ?",
                    (new_url, row["library_id"]),
                )
            current = _generation_url(sample, letter).strip()
            if current != new_url:
                column = "music_url_b" if letter == "b" else "music_url_a"
                conn.execute(
                    f"UPDATE generations SET {column} = ? WHERE id = ?",
                    (new_url, generation_id),
                )
            conn.commit()
        finally:
            conn.close()
        touched.add(generation_id)
        if kind == "fetched":
            fetched += len(group)
        else:
            switched += len(group)

    if touched:
        conn = connect(db)
        try:
            for generation_id in touched:
                _mark_complete(conn, generation_id, host)
            conn.commit()
        finally:
            conn.close()

    return {
        "switched": switched,
        "fetched": fetched,
        "failed": failed,
        "unchecked": unchecked,
    }


def _mark_complete(conn: sqlite3.Connection, generation_id: str, host: str) -> None:
    gen = conn.execute(
        "SELECT music_url_a, music_url_b FROM generations WHERE id = ?",
        (generation_id,),
    ).fetchone()
    if not gen:
        return
    urls = [url.strip() for url in (gen["music_url_a"] or "", gen["music_url_b"] or "") if url and url.strip()]
    libs = conn.execute(
        """
        SELECT ul.audio_url AS audio_url
        FROM user_library ul
        LEFT JOIN users u ON u.id = ul.user_id
        WHERE ul.generation_id = ?
          AND COALESCE(u.is_persona, 0) = 0
        """,
        (generation_id,),
    ).fetchall()
    urls.extend((row["audio_url"] or "").strip() for row in libs if (row["audio_url"] or "").strip())
    if urls and all(on_our_storage(url, host) for url in urls):
        conn.execute(
            "UPDATE generations SET storage_synced = 1 WHERE id = ?",
            (generation_id,),
        )


def print_counts(db: Path, host: str) -> None:
    print("адрес хранилища:", "задан" if host else "не задан")
    if not db.is_file():
        print("база не найдена")
        return
    conn = connect(db)
    try:
        tracks = conn.execute(
            """
            SELECT ul.audio_url AS audio_url,
                   g.id AS generation_id,
                   COALESCE(g.storage_synced, 0) AS storage_synced
            FROM user_library ul
            LEFT JOIN users u ON u.id = ul.user_id
            JOIN generations g ON g.id = ul.generation_id
            WHERE COALESCE(u.is_persona, 0) = 0
              AND (
                COALESCE(g.purchased, 0) = 1
                OR COALESCE(g.note_charged, 0) = 1
              )
            """
        ).fetchall()
        missing = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM generations g
            WHERE g.status = 'success'
              AND (
                COALESCE(g.purchased, 0) = 1
                OR COALESCE(g.note_charged, 0) = 1
              )
              AND NOT EXISTS (
                SELECT 1
                FROM user_library ul
                LEFT JOIN users u ON u.id = ul.user_id
                WHERE ul.generation_id = g.id
                  AND COALESCE(u.is_persona, 0) = 0
              )
            """
        ).fetchone()["n"]
    finally:
        conn.close()

    songs: dict[str, int] = {}
    our_files = 0
    factory_files = 0
    marked_but_factory = 0
    for row in tracks:
        songs[row["generation_id"]] = int(row["storage_synced"] or 0)
        if on_our_storage(row["audio_url"], host):
            our_files += 1
        else:
            factory_files += 1
            if int(row["storage_synced"] or 0):
                marked_but_factory += 1
    not_copied = sum(1 for synced in songs.values() if not synced)
    print(f"песен в фонотеке: {len(songs)}")
    print(f"файлов в фонотеке: {len(tracks)}")
    print(f"файлов в нашем хранилище: {our_files}")
    print(f"файлов на ссылке цеха: {factory_files}")
    print(f"песен без отметки копии: {not_copied}")
    print(f"файлов с отметкой, но ссылка цеха: {marked_but_factory}")
    print(f"купленных песен без строки в фонотеке: {missing}")


def main() -> None:
    host = public_host(ENV)
    if not host:
        print("адрес хранилища: не задан")
        return
    if not DB.is_file():
        print("база не найдена")
        return
    store = LiveStore()
    if not store.enabled():
        print("хранилище выключено")
        return
    result = repair(DB, host, store)
    print(f"переключено на нашу копию: {result['switched']}")
    print(f"забрано у цеха: {result['fetched']}")
    print(f"цех уже не отдал: {result['failed']}")
    print(f"не удалось проверить: {result['unchecked']}")
    print("--- сейчас ---")
    print_counts(DB, host)


if __name__ == "__main__":
    main()
