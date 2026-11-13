#!/usr/bin/env python3
"""Read-only: who made the double-birthday song.

Does not change songs, money, or the database.
Does not print a lyric, a song link, or a key.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = Path("/root/SongForge/data/songforge.db")


def msk(raw: str) -> str:
    text = (raw or "")[:19]
    try:
        dt = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    except ValueError:
        return text or "?"
    return (dt + timedelta(hours=3)).strftime("%d.%m %H:%M")


def clean(text: str, limit: int = 80) -> str:
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat or "—"
    return flat[: limit - 1] + "…"


def main() -> None:
    if not DB.is_file():
        print("базы нет")
        return
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, created_at, title, status, purchased, user_id, guest_id, idea
        FROM generations
        WHERE created_at >= datetime('now', '-14 day')
          AND (
            title LIKE '%Двойной праздник%'
            OR idea LIKE '%папы и сына%'
            OR idea LIKE '%Платош%'
          )
        ORDER BY created_at DESC
        LIMIT 8
        """
    ).fetchall()
    print(f"совпадений {len(rows)}")
    if not rows:
        print("песни про двойной день рождения за 14 дней нет")
        return
    for row in rows:
        user_id = (row["user_id"] or "").strip()
        print(
            f"- {msk(row['created_at'])} мск | {clean(row['title'] or '', 40)} | "
            f"{row['status']} | куплена {row['purchased']}"
        )
        print(f"  идея: {clean(row['idea'] or '', 90)}")
        if not user_id:
            guest = (row["guest_id"] or "").strip()
            tail = guest[:8] + "…" if len(guest) > 8 else (guest or "нет")
            print(f"  человек: без входа, гость {tail}")
            continue
        user = conn.execute(
            "SELECT email, display_name, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user:
            print(f"  почта: {clean(user['email'] or 'нет', 80)}")
            print(f"  имя: {clean(user['display_name'] or 'нет', 80)}")
            print(f"  аккаунт с: {msk(user['created_at'])} мск")
        else:
            print("  человек: песня привязана, строки аккаунта нет")
        ways = conn.execute(
            """
            SELECT provider FROM auth_identities
            WHERE user_id = ?
            ORDER BY created_at
            """,
            (user_id,),
        ).fetchall()
        names = [clean(item["provider"], 20) for item in ways]
        print(f"  вход: {', '.join(names) if names else 'не записан'}")
        contact = conn.execute(
            """
            SELECT max_user_id, last_channel
            FROM messenger_contacts
            WHERE user_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if contact and (contact["max_user_id"] or "").strip():
            print(
                f"  бот MAX: да, номер {clean(contact['max_user_id'], 24)}, "
                f"канал {clean(contact['last_channel'] or 'max', 16)}"
            )
        else:
            print("  бот MAX: нет")


if __name__ == "__main__":
    main()
