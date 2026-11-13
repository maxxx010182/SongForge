#!/usr/bin/env python3
"""Read-only: last songs, what we stored, and the Kie/Suno log lines.

Does not change songs, money, or the database.
Does not print keys or a full lyric. A short start of the text is enough
to see whether the letter to Kie and the letter to Suno had words.
"""

from __future__ import annotations

import gzip
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = Path("/root/SongForge/data/songforge.db")
LOG_DIR = Path("/root/.pm2/logs")
PREFIXES = (
    "songforge-out",
    "songforge-error",
    "songforge-worker-out",
    "songforge-worker-error",
)
NEEDLE = re.compile(
    r"Own lyrics kept|Pasted song kept|Production lyrics|Production ready|"
    r"sunoapi\.org create|Kie/\S+ response received|Kie \S+ HTTP |"
    r"LLM \S+/\S+ failed|asking the next|Unified package|Lyrics generated|"
    r"Lyrics attempt|All lyrics attempts failed|no text provider",
    re.I,
)
SECRET = re.compile(r"(sk-|key-|Bearer )[A-Za-z0-9_\-]{8,}")
SKIP = ("LLM provider:", "provider balance kie", "Kie credits check failed")


def msk(raw: str) -> str:
    text = (raw or "")[:19]
    try:
        dt = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    except ValueError:
        return text or "?"
    return (dt + timedelta(hours=3)).strftime("%d.%m %H:%M")


def clean(text: str, limit: int = 180) -> str:
    flat = " ".join((text or "").split())
    flat = SECRET.sub(r"\1…", flat)
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + "…"


def read_tail(path: Path, limit: int = 12000) -> list[str]:
    try:
        if path.name.endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
                lines = handle.read().splitlines()
        else:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        print(f"{path.name}: не открылся ({exc.__class__.__name__})")
        return []
    return lines[-limit:]


def log_files() -> list[Path]:
    if not LOG_DIR.is_dir():
        return []
    found = [
        path
        for path in LOG_DIR.iterdir()
        if path.is_file() and path.name.startswith(PREFIXES)
    ]
    return sorted(found, key=lambda item: item.stat().st_mtime)


def shape(lyrics: str) -> str:
    text = lyrics or ""
    lower = text.lower()
    body = [
        line
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("[")
    ]
    marks = []
    if "[verse" in lower:
        marks.append("куплет")
    if "[chorus" in lower:
        marks.append("припев")
    if not marks:
        marks.append("без меток")
    return f"{', '.join(marks)}, строк {len(body)}"


def main() -> None:
    if not DB.is_file():
        print("базы нет")
        return
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT created_at, title, status, purchased, idea, lyrics, style, fail_msg
        FROM generations
        WHERE created_at >= datetime('now', '-3 day')
        ORDER BY created_at DESC
        LIMIT 6
        """
    ).fetchall()
    print(f"заказов за 3 дня, показ {len(rows)}")
    for row in rows:
        idea = row["idea"] or ""
        lyrics = row["lyrics"] or ""
        style = row["style"] or ""
        print(
            f"- {msk(row['created_at'])} мск | {clean(row['title'] or '', 40)} | "
            f"{row['status']} | куплена {row['purchased']}"
        )
        print(f"  идея {len(idea)}: {clean(idea, 90)}")
        print(f"  слова {len(lyrics)} ({shape(lyrics)}): {clean(lyrics, 90)}")
        print(f"  звучание {len(style)}: {clean(style, 90)}")
        if row["fail_msg"]:
            print(f"  ошибка {clean(row['fail_msg'])}")
    print("--- ЖУРНАЛ ---")
    print("Полное письмо в Кие журнал не хранит. Ниже длина ответа и что ушло в Суно.")
    shown = 0
    for path in log_files():
        hits = []
        for line in read_tail(path):
            if any(bit in line for bit in SKIP):
                continue
            if NEEDLE.search(line):
                hits.append(line)
        if not hits:
            continue
        print(f"{path.name}: строк {len(hits)}")
        for line in hits[-25:]:
            print(clean(line, 220))
            shown += 1
    if shown == 0:
        print("в хвостах журнала нет строк про слова, Кие и Суно")


if __name__ == "__main__":
    main()
