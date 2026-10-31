#!/usr/bin/env python3
"""Сколько купленных песен в фонотеке лежат у нас, а сколько ещё на ссылке цеха.

Только чтение. Адреса, названия и почту не печатает.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

DB = Path(os.environ.get("SONGFORGE_DB", "/root/SongForge/data/songforge.db"))
ENV = Path(os.environ.get("SONGFORGE_ENV", "/root/SongForge/.env"))


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


def main() -> None:
    host = public_host(ENV)
    print("адрес хранилища:", "задан" if host else "не задан")
    if not DB.is_file():
        print("база не найдена")
        return

    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
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
        ours = on_our_storage(row["audio_url"], host)
        if ours:
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


if __name__ == "__main__":
    main()
