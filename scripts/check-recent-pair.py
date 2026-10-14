#!/usr/bin/env python3
"""Read-only: the latest songs, whether they share a template, and where the text came from."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

DB = Path("/root/SongForge/data/songforge.db")


def msk(raw: str) -> str:
    text = (raw or "")[:19]
    try:
        dt = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    except ValueError:
        return text
    return (dt + timedelta(hours=3)).strftime("%d.%m %H:%M")


def lines_of(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def show(label: str, rows: list[str]) -> None:
    if not rows:
        print(f"  {label}: пусто")
        return
    print(f"  {label}:")
    for line in rows:
        print(f"   {line[:160]}")


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, created_at, title, user_id, purchased, note_charged,
               lyrics, idea
        FROM generations
        WHERE status = 'success'
        ORDER BY created_at DESC
        LIMIT 4
        """
    ).fetchall()
    print(f"последних готовых песен: {len(rows)}")
    packed = []
    for i, row in enumerate(rows, start=1):
        uid = row["user_id"] or ""
        name = ""
        providers = ""
        bot = "нет"
        if uid:
            user = conn.execute(
                "SELECT display_name FROM users WHERE id = ?",
                (uid,),
            ).fetchone()
            name = ((user["display_name"] if user else "") or "").strip()
            providers = ",".join(
                r["provider"]
                for r in conn.execute(
                    "SELECT provider FROM auth_identities WHERE user_id = ?",
                    (uid,),
                )
            )
            contact = conn.execute(
                """
                SELECT last_channel FROM messenger_contacts
                WHERE user_id = ? AND TRIM(COALESCE(max_user_id,'')) != ''
                LIMIT 1
                """,
                (uid,),
            ).fetchone()
            if contact:
                bot = contact["last_channel"] or "max"
        idea = row["idea"] or ""
        lyrics = row["lyrics"] or ""
        head = idea.lstrip()[:24]
        origin = "бот" if head.startswith("Песня ") else "описание на сайте"
        same = "да" if " ".join(idea.split()) == " ".join(lyrics.split()) else "нет"
        print(
            f"{i}. {msk(row['created_at'])} мск | {str(row['title'] or '')[:42]} | "
            f"куплена {row['purchased']} | {name or 'без имени'} | "
            f"вход {providers or '-'} | бот {bot} | текст {origin} | "
            f"идея=песня {same} | знаков {len(lyrics)}"
        )
        show("начало идеи", lines_of(idea)[:6])
        show("начало песни", lines_of(lyrics)[:8])
        packed.append(row)

    if len(packed) < 2:
        return
    a, b = packed[0], packed[1]
    la = "\n".join(lines_of(a["lyrics"]))
    lb = "\n".join(lines_of(b["lyrics"]))
    ia = "\n".join(lines_of(a["idea"]))
    ib = "\n".join(lines_of(b["idea"]))
    print("--- сравнение двух последних ---")
    print("один аккаунт:", "да" if a["user_id"] and a["user_id"] == b["user_id"] else "нет")
    print(f"похожесть песен: {SequenceMatcher(None, la, lb).ratio():.2f}")
    print(f"похожесть идей: {SequenceMatcher(None, ia, ib).ratio():.2f}")
    set_a = {line.lower() for line in lines_of(a["lyrics"]) if not line.startswith("[")}
    set_b = {line.lower() for line in lines_of(b["lyrics"]) if not line.startswith("[")}
    shared = sorted(set_a & set_b)
    print(f"одинаковых строк: {len(shared)}")
    for line in shared[:12]:
        print(f"   {line[:160]}")


if __name__ == "__main__":
    main()
