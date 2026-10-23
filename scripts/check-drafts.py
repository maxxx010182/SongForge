#!/usr/bin/env python3
"""Read-only: drafts that have text but never reached the music cabinet."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = Path("/root/SongForge/data/songforge.db")
LOGS = [
    Path("/root/.pm2/logs/songforge-out.log"),
    Path("/root/.pm2/logs/songforge-error.log"),
    Path("/root/.pm2/logs/songforge-worker-out.log"),
    Path("/root/.pm2/logs/songforge-worker-error.log"),
]
MARKERS = (
    "Production ready",
    "Music start",
    "Music provider",
    "sunoapi.org create",
    "sunoapi.org task",
    "sunoapi.org error",
    "sunoapi.org create failed",
    "sunoapi.org create timeout",
    "APIPass",
    "music start failed",
    "create-song failed",
    "insufficient",
)
SECRET = re.compile(r"(sk-|key-|Bearer )[A-Za-z0-9_\-]{8,}")


def msk(raw: str) -> str:
    text = (raw or "")[:19]
    try:
        dt = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    except ValueError:
        return text
    return (dt + timedelta(hours=3)).strftime("%d.%m %H:%M")


def clean(line: str) -> str:
    flat = " ".join(line.split())
    return SECRET.sub(r"\1…", flat)[:220]


def tail(path: Path, max_bytes: int = 1_500_000) -> list[str]:
    if not path.is_file():
        return []
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(size - max_bytes)
        data = handle.read().decode("utf-8", errors="replace")
    return data.splitlines()


def name_for(conn: sqlite3.Connection, user_id: str | None) -> str:
    if not user_id:
        return "без аккаунта"
    row = conn.execute(
        "SELECT display_name FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    label = ((row["display_name"] if row else "") or "").strip()
    return label or "без имени"


def print_row(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    task = (row["task_id"] or "").strip()
    fail = " ".join((row["fail_msg"] or "").split())[:80]
    print(
        f"- {msk(row['created_at'])} мск | {str(row['title'] or '')[:32]} | "
        f"{row['status']} | задача {'есть' if task else 'нет'} | "
        f"музыка {row['music_provider'] or '-'} | "
        f"текст {row['lyrics_len'] or 0} | стиль {row['style_len'] or 0} | "
        f"нота {row['note_charged']} | {name_for(conn, row['user_id'])}"
        + (f" | {fail}" if fail else "")
    )


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    drafts = conn.execute(
        """
        SELECT created_at, title, status, task_id, music_provider, fail_msg,
               length(lyrics) AS lyrics_len, length(style) AS style_len,
               note_charged, user_id
        FROM generations
        WHERE lower(COALESCE(status, '')) = 'planned'
           OR task_id IS NULL
           OR trim(task_id) = ''
        ORDER BY created_at DESC
        LIMIT 8
        """
    ).fetchall()
    latest = conn.execute(
        """
        SELECT created_at, title, status, task_id, music_provider, fail_msg,
               length(lyrics) AS lyrics_len, length(style) AS style_len,
               note_charged, user_id
        FROM generations
        ORDER BY created_at DESC
        LIMIT 5
        """
    ).fetchall()
    print(f"черновики, музыка не запускалась: {len(drafts)}")
    for row in drafts:
        print_row(conn, row)
    print("последние заказы:")
    for row in latest:
        print_row(conn, row)

    hits: list[str] = []
    for path in LOGS:
        for line in tail(path):
            if any(marker in line for marker in MARKERS):
                hits.append(clean(line))
    print(f"строки журнала про музыку: {min(len(hits), 25)} из {len(hits)}")
    for line in hits[-25:]:
        print(line)


if __name__ == "__main__":
    main()
