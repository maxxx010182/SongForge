#!/usr/bin/env python3
"""Read-only: the latest song and the Kie lines in our logs."""

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
    "LLM ",
    "Kie ",
    "Unified package",
    "Production lyrics",
    "Production ready",
    "Pasted song",
    "asking the next",
    "LlmUnavailable",
    "S3 mirror",
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
    return SECRET.sub(r"\1…", flat)[:240]


def tail(path: Path, limit: int = 8000) -> list[str]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT created_at, title, status, purchased, note_charged,
               fail_msg, lyrics, idea, user_id
        FROM generations
        ORDER BY created_at DESC
        LIMIT 3
        """
    ).fetchall()
    print(f"последних заказов: {len(rows)}")
    for row in rows:
        name = ""
        if row["user_id"]:
            user = conn.execute(
                "SELECT display_name FROM users WHERE id = ?",
                (row["user_id"],),
            ).fetchone()
            name = ((user["display_name"] if user else "") or "").strip()
        idea = (row["idea"] or "").strip().splitlines()
        print(
            f"- {msk(row['created_at'])} мск | {str(row['title'] or '')[:40]} | "
            f"{row['status']} | куплена {row['purchased']} | нота {row['note_charged']} | "
            f"{name or 'без имени'} | текст {len(row['lyrics'] or '')}"
        )
        if row["fail_msg"]:
            print(f"  ошибка {clean(row['fail_msg'])}")
        if idea:
            print(f"  идея {clean(idea[0])}")
    print("--- LOG ---")
    shown = 0
    for path in LOGS:
        lines = tail(path)
        if not lines:
            print(f"{path.name}: нет файла")
            continue
        hit = [line for line in lines if any(m in line for m in MARKERS)]
        print(f"{path.name}: строк {len(hit)}")
        for line in hit[-30:]:
            print(clean(line))
            shown += 1
    if shown == 0:
        print("в хвостах журналов нет строк про Кие")


if __name__ == "__main__":
    main()
