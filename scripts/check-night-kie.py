#!/usr/bin/env python3
"""Read-only: night orders and whether a reserve model was asked."""

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
# 15 Oct 21:00 MSK through 16 Oct 12:00 MSK. Log clocks are UTC.
START = "2026-10-15 18:00:00"
END = "2026-10-16 09:00:00"
MARKERS = (
    "LLM ",
    "Music provider",
    "LlmUnavailable",
    "Production ",
    "asking the next",
    "fallback",
    "failed",
    "timeout",
    "Kie ",
    "Exception",
    "Error",
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
    return SECRET.sub(r"\1…", flat)[:260]


def in_window(line: str) -> bool:
    stamp = line[:19]
    return START <= stamp <= END


def main() -> None:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, created_at, title, status, purchased, note_charged,
               fail_code, fail_msg, lyrics, idea, user_id
        FROM generations
        WHERE created_at >= ? AND created_at <= ?
        ORDER BY created_at
        """,
        (START, END),
    ).fetchall()
    print(f"заказов за ночь: {len(rows)}")
    for row in rows:
        name = ""
        earlier = 0
        providers = ""
        if row["user_id"]:
            user = conn.execute(
                "SELECT display_name FROM users WHERE id = ?",
                (row["user_id"],),
            ).fetchone()
            name = ((user["display_name"] if user else "") or "").strip()
            earlier = conn.execute(
                """
                SELECT COUNT(*) FROM generations
                WHERE user_id = ? AND created_at < ?
                """,
                (row["user_id"], row["created_at"]),
            ).fetchone()[0]
            auth = conn.execute(
                """
                SELECT provider FROM auth_identities
                WHERE user_id = ? ORDER BY created_at
                """,
                (row["user_id"],),
            ).fetchall()
            providers = ",".join(item["provider"] for item in auth)
        idea = (row["idea"] or "").strip().splitlines()
        idea_line = idea[0][:80] if idea else ""
        print(
            f"- {msk(row['created_at'])} мск | заход {earlier + 1} | "
            f"{str(row['title'] or '')[:40]} | {row['status']} | "
            f"куплена {row['purchased']} | нота {row['note_charged']} | "
            f"{name or 'без имени'} | {providers or 'вход не записан'} | "
            f"текст {len(row['lyrics'] or '')} | {row['id']}"
        )
        if idea_line:
            print(f"  идея {idea_line}")
        if row["fail_code"] or row["fail_msg"]:
            print(
                f"  сбой {row['fail_code'] or ''} "
                f"{clean(row['fail_msg'] or '')[:180]}"
            )
    print("--- LOG ---")
    for path in LOGS:
        if not path.is_file():
            print(f"{path.name}: нет файла")
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        picked = [
            clean(line)
            for line in lines
            if in_window(line) and any(marker in line for marker in MARKERS)
        ]
        print(f"{path.name}: строк {len(picked)}")
        for line in picked[-60:]:
            print(line)


if __name__ == "__main__":
    main()
