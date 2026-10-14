#!/usr/bin/env python3
"""Read-only: were the two morning songs one account, and what sits at the end of the text."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path("/root/SongForge/data/songforge.db")
SINCE = "2026-10-13T21:00:00"
HINTS = (
    "совет",
    "жанр",
    "настроен",
    "стиль",
    "промпт",
    "задани",
    "suno",
    "bpm",
    "темп",
    "не использ",
    "для генерац",
)


def tail(text: str, n: int = 12) -> list[str]:
    lines = [line.rstrip() for line in (text or "").splitlines() if line.strip()]
    return lines[-n:]


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, substr(created_at,1,19) AS at, title, user_id, guest_id,
               purchased, lyrics, idea
        FROM generations
        WHERE created_at >= ? AND status = 'success'
        ORDER BY created_at
        """,
        (SINCE,),
    ).fetchall()
    ids = [row["user_id"] or "" for row in rows]
    print("один аккаунт:", "да" if ids and len(set(ids)) == 1 and ids[0] else "нет")
    for row in rows:
        uid = row["user_id"] or ""
        providers = []
        channel = ""
        if uid:
            providers = [
                r["provider"]
                for r in conn.execute(
                    "SELECT provider FROM auth_identities WHERE user_id = ?",
                    (uid,),
                )
            ]
            contact = conn.execute(
                """
                SELECT last_channel,
                       CASE WHEN TRIM(COALESCE(max_user_id,'')) != '' THEN 1 ELSE 0 END AS has_max
                FROM messenger_contacts WHERE user_id = ?
                """,
                (uid,),
            ).fetchone()
            if contact:
                channel = f"{contact['last_channel'] or '-'} max={contact['has_max']}"
        print(
            f"- {row['at']} | куплена {row['purchased']} | "
            f"вход {','.join(providers) or 'не видно'} | бот {channel or 'нет'}"
        )
        print("  конец идеи:")
        for line in tail(row["idea"]):
            mark = " !" if any(h in line.lower() for h in HINTS) else ""
            print(f"   {line[:160]}{mark}")
        print("  конец текста песни:")
        for line in tail(row["lyrics"]):
            mark = " !" if any(h in line.lower() for h in HINTS) else ""
            print(f"   {line[:160]}{mark}")


if __name__ == "__main__":
    main()
