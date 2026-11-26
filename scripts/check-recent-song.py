#!/usr/bin/env python3
"""Read-only: a person made a song, Kie tried more than once, the result was not seen.

Does not change songs, money, or the database.
Does not print a name, a mail, a lyric, a title, a task number, a voice number, or a key.
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
HOURS = 24
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
NGINX_STAMP = re.compile(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})")
SAFE_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")
PATHS = ("/api/produce", "/api/create-song", "/api/music/start", "/api/music/status")


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


def voice_flag(plan_json: str) -> str:
    try:
        plan = json.loads(plan_json or "{}")
    except json.JSONDecodeError:
        return "план не читается"
    if (plan.get("own_voice_id") or "").strip():
        return "да"
    return "нет"


def sound(url_a: int, url_b: int) -> str:
    count = (1 if url_a else 0) + (1 if url_b else 0)
    return {0: "нет", 1: "один", 2: "оба"}[count]


def minutes(value) -> str:
    if value is None or value == "":
        return "—"
    try:
        return str(int(float(value) // 60)) + ":" + f"{int(float(value) % 60):02d}"
    except (TypeError, ValueError):
        return "—"


def fail_label(code: str) -> str:
    text = (code or "").strip()
    if not text:
        return "нет"
    if SAFE_CODE.fullmatch(text):
        return text
    return "есть"


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
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(hours=HOURS + 3)
    return naive >= cutoff or (naive - timedelta(hours=3)) >= cutoff


def phrase(line: str) -> str:
    flat = " ".join((line or "").split())
    found = re.search(r"LLM (\S+/\S+) failed \(([^)]+)\)", flat)
    if found:
        return f"текст {found.group(1)} ошибка ({found.group(2)})"
    found = re.search(r"LLM (\S+/\S+) no text after (\d+)s", flat)
    if found:
        return f"текст {found.group(1)} молчал {found.group(2)} с, спросили следующую"
    found = re.search(
        r"Lyrics generated via (\S+) \(len=(\d+), lazy=(?:True|False)\)",
        flat,
    )
    if found:
        return f"текст готов через {found.group(1)}, {found.group(2)} знаков"
    if "All lyrics attempts failed" in flat:
        return "все попытки текста кончились ошибкой"
    if "Production ready" in flat:
        ready = re.search(r"instrumental=(?:True|False) duration=\d+", flat)
        extra = f" | {ready.group(0)}" if ready else ""
        return "текст на страницу отдан" + extra
    if "Saved text shown" in flat:
        found = re.search(r"len=(\d+)", flat)
        extra = f", {found.group(1)} знаков" if found else ""
        return "показали уже сохранённый текст" + extra
    found = re.search(r"Music provider (\w+) failed", flat)
    if found:
        return f"цех {found.group(1)} песню не взял"
    found = re.search(r"Music provider fallback: using (\w+)", flat)
    if found:
        return f"песня ушла в запасной цех {found.group(1)}"
    if "sunoapi.org task created" in flat:
        return "задача создана в sunoapi"
    if "APIPass task created" in flat:
        return "задача создана в apipass"
    if "music start failed" in flat:
        return "запуск песни упал"
    found = re.search(r"Music poll failed \(([^)]+)\)", flat)
    if found:
        return f"опрос песни упал ({found.group(1)})"
    if "cover copy failed" in flat:
        return "обложка не скопировалась"
    return ""


def log_names(path: Path) -> bool:
    name = path.name
    return name.startswith(("songforge-out", "songforge-error", "songforge-worker-out", "songforge-worker-error"))


def main() -> None:
    start = since()
    print(f"окно: последние {HOURS} часов, с {msk_from(start)} мск")
    if not DB.is_file():
        print("базы нет")
        return
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT created_at, status, purchased, note_charged, task_id,
               music_provider, plan_json, fail_code,
               LENGTH(TRIM(COALESCE(lyrics, ''))) AS lyric_len,
               LENGTH(TRIM(COALESCE(music_url_a, ''))) AS url_a,
               LENGTH(TRIM(COALESCE(music_url_b, ''))) AS url_b,
               duration_a, duration_b
        FROM generations
        WHERE created_at >= ?
        ORDER BY created_at
        """,
        (start.strftime("%Y-%m-%dT%H:%M:%S"),),
    ).fetchall()
    print(f"песен в базе: {len(rows)}")
    for index, row in enumerate(rows, start=1):
        task = "есть" if (row["task_id"] or "").strip() else "нет"
        print(
            f"- {index}. {msk(row['created_at'])} мск | {row['status']} | "
            f"текст {int(row['lyric_len'] or 0)} знаков | задача {task} | "
            f"цех {row['music_provider'] or '—'} | звук {sound(row['url_a'], row['url_b'])} | "
            f"{minutes(row['duration_a'])} и {minutes(row['duration_b'])} | "
            f"нота {'да' if row['note_charged'] else 'нет'} | "
            f"куплена {'да' if row['purchased'] else 'нет'} | "
            f"сбой {fail_label(row['fail_code'])} | "
            f"свой голос {voice_flag(row['plan_json'])}"
        )

    print("--- ЖУРНАЛ САЙТА ---")
    hits = 0
    paths = []
    if LOG_DIR.is_dir():
        paths = sorted(path for path in LOG_DIR.iterdir() if path.is_file() and log_names(path))
    if not paths:
        print("журнала сайта нет")
    for path in paths:
        found = 0
        for line in tail_lines(path):
            moment = log_moment(line)
            if moment is not None and moment < start:
                continue
            text = phrase(line)
            if not text:
                continue
            if found == 0:
                print(f"файл {path.name}")
            print(f"  {text}")
            found += 1
            hits += 1
            if found >= 60:
                print("  …дальше в этом файле обрезано")
                break
    if hits == 0:
        print("строк про текст и песню нет")

    print("--- ПРОКСИ ---")
    proxy = 0
    if not NGINX.is_file():
        print("журнала прокси нет")
    else:
        for line in tail_lines(NGINX):
            if "timed out" not in line:
                continue
            path = next((item for item in PATHS if item in line), "")
            if not path:
                continue
            moment = nginx_moment(line)
            if moment is not None and not recent_clock(moment):
                continue
            stamp = moment.strftime("%d.%m %H:%M") if moment else "?"
            print(f"- {stamp} | прокси оборвал ожидание {path}")
            proxy += 1
            if proxy >= 15:
                break
        if proxy == 0:
            print("обрыва прокси нет")
    print("конец")


if __name__ == "__main__":
    main()
