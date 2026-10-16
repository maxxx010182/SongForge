#!/usr/bin/env python3
"""Read-only: the two morning songs and any failed order beside them."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = Path("/root/SongForge/data/songforge.db")
LOG_DIR = Path("/root/.pm2/logs")
IDS = (
    "f3e416e9-4a56-451b-8896-cce2c0b73e5c",
    "3dca8661-1ce9-4e6b-8d8b-0bbacb9e6633",
)
START = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)
END = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
SECRET = re.compile(r"(sk-|key-|Bearer )[A-Za-z0-9_\-]{8,}")


def parse_utc(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(text[:32])
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def msk(stamp: datetime | None) -> str:
    if stamp is None:
        return "?"
    return (stamp + timedelta(hours=3)).strftime("%d.%m %H:%M")


def clean(line: str) -> str:
    return SECRET.sub(r"\1…", " ".join(line.split()))[:260]


def show(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
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
            "SELECT COUNT(*) FROM generations WHERE user_id = ? AND created_at < ?",
            (row["user_id"], row["created_at"]),
        ).fetchone()[0]
        auth = conn.execute(
            "SELECT provider FROM auth_identities WHERE user_id = ? ORDER BY created_at",
            (row["user_id"],),
        ).fetchall()
        providers = ",".join(item["provider"] for item in auth)
    idea = (row["idea"] or "").strip().splitlines()
    print(
        f"- {msk(parse_utc(row['created_at']))} мск | заход {earlier + 1} | "
        f"{str(row['title'] or '')[:40]} | {row['status']} | "
        f"куплена {row['purchased']} | нота {row['note_charged']} | "
        f"{name or 'без имени'} | {providers or 'вход не записан'} | "
        f"текст {len(row['lyrics'] or '')} | музыка {1 if row['music_url_a'] else 0} | "
        f"{row['id']}"
    )
    if idea:
        print(f"  идея {idea[0][:90]}")
    if row["fail_code"] or row["fail_msg"]:
        print(f"  сбой {row['fail_code'] or ''} {clean(row['fail_msg'] or '')[:180]}")


def main() -> None:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, created_at, title, status, purchased, note_charged,
               fail_code, fail_msg, lyrics, idea, user_id, music_url_a
        FROM generations
        """
    ).fetchall()
    night = []
    for row in rows:
        stamp = parse_utc(row["created_at"])
        if stamp is not None and START <= stamp <= END:
            night.append(row)
    night.sort(key=lambda row: row["created_at"])
    print(f"заказов с вечера 15.10 до утра 16.10: {len(night)}")
    for row in night:
        show(conn, row)
    print("--- НЕ УСПЕХ ЗА ДВОЕ СУТОК ---")
    bad = []
    for row in rows:
        stamp = parse_utc(row["created_at"])
        if stamp is None or stamp < START - timedelta(days=1):
            continue
        if (row["status"] or "") != "success" or not (row["lyrics"] or "").strip():
            bad.append(row)
    bad.sort(key=lambda row: row["created_at"])
    print(f"без готового текста или не success: {len(bad)}")
    for row in bad[-12:]:
        show(conn, row)
    print("--- LOG ---")
    files = sorted(LOG_DIR.glob("songforge*.log*"))
    if not files:
        print("журналов нет")
        return
    for path in files:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        picked = []
        for line in lines:
            stamp = parse_utc(line[:19].replace(",", "."))
            interesting = any(
                marker in line
                for marker in (
                    "LLM ",
                    "produce failed",
                    "music start failed",
                    "Music provider",
                    "asking the next",
                    "All lyrics",
                    "LlmUnavailable",
                    "Production ",
                )
            ) or any(item in line for item in IDS)
            if not interesting:
                continue
            if stamp is not None and not (START <= stamp <= END) and not any(
                item in line for item in IDS
            ):
                continue
            if stamp is None and not any(item in line for item in IDS):
                continue
            picked.append(clean(line))
        print(f"{path.name}: строк {len(picked)}")
        for line in picked[-40:]:
            print(line)


if __name__ == "__main__":
    main()
