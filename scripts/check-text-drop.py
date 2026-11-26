#!/usr/bin/env python3
"""Read-only: the text button showed an error, but Kie may already have written.

Does not change songs, money, or the database.
Does not print a name, a mail, a lyric, a title, a voice number, or a key.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = Path("/root/SongForge/data/songforge.db")
LOG_DIR = Path("/root/.pm2/logs")
NGINX = Path("/var/log/nginx/error.log")
HOURS = 8
SECRET = re.compile(
    r"(sk-|key-|Bearer |personaId[\"']?\s*[:=]\s*[\"']?)[A-Za-z0-9_\-]{6,}",
    re.I,
)
EMAIL = re.compile(r"[\w.+\-]+@[\w.\-]+")
FAIL_LINE = re.compile(r"LLM \S+/\S+ failed \([^)]+\)")
NEXT_LINE = re.compile(r"LLM \S+/\S+ no text after \d+s; asking the next model")
LYRICS_LINE = re.compile(r"Lyrics generated via \S+ \(len=\d+, lazy=(?:True|False)\)")
READY_LINE = re.compile(r"instrumental=(?:True|False) duration=\d+")
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
NGINX_STAMP = re.compile(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})")


def msk_from(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (moment.astimezone(timezone.utc) + timedelta(hours=3)).strftime("%d.%m %H:%M")


def msk(raw: str) -> str:
    text = (raw or "")[:19]
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return text or "?"
    return msk_from(moment)


def since() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=HOURS)


def clean(text: str) -> str:
    flat = " ".join((text or "").split())
    for pattern in (FAIL_LINE, NEXT_LINE, LYRICS_LINE):
        found = pattern.search(flat)
        if found:
            flat = found.group(0)
            break
    else:
        ready = READY_LINE.search(flat)
        if ready and "Production ready" in flat:
            flat = "Production ready | " + ready.group(0)
        elif "All lyrics attempts" in flat:
            flat = "All lyrics attempts failed"
        else:
            flat = flat[:120]
    flat = SECRET.sub(r"\1…", flat)
    return EMAIL.sub("почта", flat)


def voice_flag(plan_json: str) -> str:
    try:
        plan = json.loads(plan_json or "{}")
    except json.JSONDecodeError:
        return "план не читается"
    if (plan.get("own_voice_id") or "").strip():
        return "да"
    return "нет"


def tail_lines(path: Path) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 2_000_000))
            data = handle.read().decode("utf-8", "replace")
    except OSError as exc:
        print(f"{path.name}: не открылся ({exc.__class__.__name__})")
        return []
    return data.splitlines()[-8000:]


def log_moment(line: str) -> datetime | None:
    found = STAMP.search(line)
    if not found:
        return None
    try:
        moment = datetime.strptime(found.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return moment.replace(tzinfo=timezone.utc)


def nginx_moment(line: str) -> datetime | None:
    found = NGINX_STAMP.search(line)
    if not found:
        return None
    try:
        return datetime.strptime(found.group(1), "%Y/%m/%d %H:%M:%S")
    except ValueError:
        return None


def recent_clock(naive: datetime) -> bool:
    """Часы в журнале могут быть UTC или московскими. Свежую строку не выбрасываем."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(hours=12)
    return naive >= cutoff or (naive - timedelta(hours=3)) >= cutoff


def interesting(line: str) -> bool:
    return any(
        part in line
        for part in (
            "LLM ",
            "asking the next",
            "Lyrics generated",
            "Production ready",
            "All lyrics attempts",
            "no text provider",
        )
    )


def main() -> None:
    start = since()
    start_text = start.strftime("%Y-%m-%dT%H:%M:%S")
    print(f"окно: последние {HOURS} часов, с {msk_from(start)} мск")
    if not DB.is_file():
        print("базы нет")
        return
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT created_at, status, purchased, note_charged, task_id,
               music_provider, plan_json,
               LENGTH(TRIM(COALESCE(lyrics, ''))) AS lyric_len
        FROM generations
        WHERE created_at >= ?
        ORDER BY created_at
        """,
        (start_text,),
    ).fetchall()
    print(f"песен в базе: {len(rows)}")
    saved_text = 0
    for index, row in enumerate(rows, start=1):
        length = int(row["lyric_len"] or 0)
        task = "есть" if (row["task_id"] or "").strip() else "нет"
        if length > 0 and task == "нет":
            saved_text += 1
        print(
            f"- {index}. {msk(row['created_at'])} мск | {row['status']} | "
            f"текст {length} знаков | задача {task} | "
            f"цех {row['music_provider'] or '—'} | "
            f"свой голос {voice_flag(row['plan_json'])}"
        )
    if saved_text:
        print(f"текст у нас есть, в цех не уходил: {saved_text}")
    else:
        print("текста, который остался только у нас, нет")

    print("--- ЖУРНАЛ САЙТА ---")
    hits = 0
    paths = []
    if LOG_DIR.is_dir():
        paths = sorted(
            path
            for path in LOG_DIR.iterdir()
            if path.is_file()
            and (
                path.name.startswith("songforge-out")
                or path.name.startswith("songforge-error")
            )
        )
    if not paths:
        print("журнала сайта нет")
    for path in paths:
        found = 0
        for line in tail_lines(path):
            moment = log_moment(line)
            if moment is not None and moment < start:
                continue
            if not interesting(line):
                continue
            if found == 0:
                print(f"файл {path.name}")
            print(f"  {clean(line)}")
            found += 1
            hits += 1
            if found >= 40:
                print("  …дальше в этом файле обрезано")
                break
        if found == 0 and path.stat().st_size:
            pass
    if hits == 0:
        print("строк про текст нет")

    print("--- ПРОКСИ ---")
    proxy = 0
    if not NGINX.is_file():
        print("журнала прокси нет")
    else:
        for line in tail_lines(NGINX):
            if "timed out" not in line or "/api/produce" not in line:
                continue
            moment = nginx_moment(line)
            if moment is not None and not recent_clock(moment):
                continue
            stamp = moment.strftime("%d.%m %H:%M") if moment else "?"
            print(f"- {stamp} | прокси оборвал ожидание текста")
            proxy += 1
            if proxy >= 10:
                break
        if proxy == 0:
            print("обрыва прокси на тексте нет")
    print("конец")


if __name__ == "__main__":
    main()
