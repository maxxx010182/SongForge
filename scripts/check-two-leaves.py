#!/usr/bin/env python3
"""Read-only path of the last two people who started a song.

Does not change songs, money, or the database.
Does not print a name, a mail, a lyric, a title, a task number, or a key.
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
HOURS = 72
SAFE_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
NGINX_STAMP = re.compile(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})")


def parse_utc(raw: str) -> datetime | None:
    text = (raw or "")[:19]
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def msk(moment: datetime | None) -> str:
    if moment is None:
        return "?"
    return (moment + timedelta(hours=3)).strftime("%d.%m %H:%M")


def minutes(value) -> str:
    if value is None or value == "":
        return "—"
    try:
        whole = int(float(value))
    except (TypeError, ValueError):
        return "—"
    return f"{whole // 60}:{whole % 60:02d}"


def sound(url_a: int, url_b: int) -> str:
    count = (1 if url_a else 0) + (1 if url_b else 0)
    return {0: "нет", 1: "один", 2: "оба"}[count]


def fail_label(code: str) -> str:
    text = (code or "").strip()
    if not text:
        return "нет"
    if SAFE_CODE.fullmatch(text):
        return text
    return "есть"


def plan_bits(raw: str) -> str:
    try:
        plan = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return "план не читается"
    if not isinstance(plan, dict):
        return "план не читается"
    words = "без слов" if plan.get("instrumental") else "со словами"
    vocal = str(plan.get("vocal") or "").strip().lower()
    if vocal not in {"male", "female", "duet", "auto"}:
        vocal = "—"
    try:
        duration = int(plan.get("duration_sec") or 0)
    except (TypeError, ValueError):
        duration = 0
    return f"{words} | голос {vocal} | просили {duration} с"


def stage(row: sqlite3.Row) -> str:
    status = (row["status"] or "").strip().lower()
    lyric_len = int(row["lyric_len"] or 0)
    task = bool((row["task_id"] or "").strip())
    audio = bool(row["url_a"] or row["url_b"])
    if status == "success" and audio and lyric_len == 0:
        return "песня есть, сохранённых слов нет"
    if status == "success" and audio:
        return "песня есть"
    if status == "error":
        return "цех вернул ошибку, песни нет"
    if status in {"generating", "processing"} and task:
        return "музыка запущена, ответ ещё не записан"
    if lyric_len and not task:
        return "текст сохранён, до цеха не дошло"
    if not lyric_len and not task:
        return "заказа нет: ни текста, ни цеха"
    return f"статус {status or 'пусто'}"


def phrase(line: str) -> str:
    flat = " ".join(line.split())
    found = re.search(r"LLM (\S+)/(\S+) failed \(([^)]+)\)", flat)
    if found:
        return f"текст {found.group(1)}/{found.group(2)} ошибка ({found.group(3)})"
    found = re.search(r"LLM (\S+)/(\S+) no text after (\d+)s", flat)
    if found:
        return f"текст {found.group(1)}/{found.group(2)} молчал {found.group(3)} с"
    found = re.search(r"Own lyrics kept without a rewrite \(len=(\d+)\)", flat)
    if found:
        return f"свой текст оставлен, {found.group(1)} знаков"
    found = re.search(r"Pasted song kept without a rewrite \(len=(\d+)\)", flat)
    if found:
        return f"вставленная песня оставлена, {found.group(1)} знаков"
    found = re.search(
        r"Unified lyrics engine: source=(\S+).*lyrics_len=(\d+)",
        flat,
    )
    if found:
        return f"текст собран, источник {found.group(1)}, {found.group(2)} знаков"
    if "Unified package stopped: no text provider answered" in flat:
        return "текст не собрался: модель не ответила"
    found = re.search(r"Unified package (\S+): empty/unparseable", flat)
    if found:
        return f"текст {found.group(1)} пустой ответ"
    found = re.search(r"Unified package (\S+): lazy lyrics \(len=(\d+)\)", flat)
    if found:
        return f"текст {found.group(1)} слишком похож на просьбу, {found.group(2)} знаков"
    found = re.search(r"Unified package (\S+): incomplete structure/len \(len=(\d+)\)", flat)
    if found:
        return f"текст {found.group(1)} короткий, {found.group(2)} знаков, всё равно оставлен"
    if "expected Russian lyrics" in flat:
        return "текст вышел не на русском, была ещё попытка"
    if "All lyrics attempts failed" in flat:
        return "все попытки текста кончились"
    found = re.search(r"Production ready:.*instrumental=(True|False) duration=(\d+)", flat)
    if found:
        words = "без слов" if found.group(1) == "True" else "со словами"
        return f"текст на страницу отдан | {words} | {found.group(2)} с"
    found = re.search(
        r"Music start duration: (\d+) sec \(requested=(\d+) sung_len=(\d+)\)",
        flat,
    )
    if found:
        return (
            f"в цех просили {found.group(1)} с, "
            f"в описании {found.group(2)} с, спето знаков {found.group(3)}"
        )
    found = re.search(r"Music provider (\w+) failed", flat)
    if found:
        return f"цех {found.group(1)} не принял"
    found = re.search(r"Music provider fallback: using (\w+)", flat)
    if found:
        return f"цех перешёл на {found.group(1)}"
    found = re.search(r"sunoapi\.org create:.*lyrics_len=(\d+)", flat)
    if found:
        return f"в sunoapi ушло {found.group(1)} знаков текста"
    if "sunoapi.org task created" in flat:
        return "задача создана в sunoapi"
    if "APIPass task created" in flat:
        return "задача создана в apipass"
    if "Music poll failed" in flat:
        return "опрос песни упал"
    return ""


def tail_lines(path: Path, size: int = 3_000_000) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            total = handle.tell()
            handle.seek(max(0, total - size))
            raw = handle.read(size)
    except OSError:
        return []
    text = raw.decode("utf-8", errors="replace")
    if total > size:
        cut = text.find("\n")
        if cut >= 0:
            text = text[cut + 1 :]
    return text.splitlines()


def log_moment(line: str) -> datetime | None:
    found = STAMP.match(line)
    if not found:
        return None
    try:
        return datetime.strptime(found.group(1), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def nginx_moment(line: str) -> datetime | None:
    found = NGINX_STAMP.match(line)
    if not found:
        return None
    try:
        return datetime.strptime(found.group(1), "%Y/%m/%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def journal(start: datetime, end: datetime) -> list[str]:
    lines: list[str] = []
    names = (
        "songforge-out",
        "songforge-error",
        "songforge-worker-out",
        "songforge-worker-error",
    )
    if LOG_DIR.is_dir():
        paths = sorted(
            path
            for path in LOG_DIR.iterdir()
            if path.is_file() and path.name.startswith(names)
        )
    else:
        paths = []
    for path in paths:
        kept = 0
        for line in tail_lines(path):
            moment = log_moment(line)
            if moment is None or moment < start or moment > end:
                continue
            text = phrase(line)
            if not text:
                continue
            lines.append(f"  {msk(moment)} | {text}")
            kept += 1
            if kept >= 30:
                lines.append("  …дальше в этом файле обрезано")
                break
    if NGINX.is_file():
        kept = 0
        for line in tail_lines(NGINX, 1_000_000):
            if "upstream timed out" not in line:
                continue
            if not any(path in line for path in ("/api/produce", "/api/music/start", "/api/create-song")):
                continue
            moment = nginx_moment(line)
            if moment is None or moment < start or moment > end:
                continue
            which = "текст" if "/api/produce" in line or "/api/create-song" in line else "песня"
            lines.append(f"  {msk(moment)} | прокси оборвал ожидание, {which}")
            kept += 1
            if kept >= 8:
                break
    return lines


def main() -> None:
    start = datetime.now(timezone.utc) - timedelta(hours=HOURS)
    print(f"окно: последние {HOURS} часа, с {msk(start)} мск")
    if not DB.is_file():
        print("базы нет")
        return
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    people = conn.execute(
        """
        SELECT
            CASE
                WHEN TRIM(COALESCE(user_id, '')) != '' THEN 'u:' || user_id
                WHEN TRIM(COALESCE(guest_id, '')) != '' THEN 'g:' || guest_id
                ELSE 'anon'
            END AS who,
            MAX(created_at) AS last_at
        FROM generations
        WHERE created_at >= ?
        GROUP BY who
        ORDER BY last_at DESC
        LIMIT 2
        """,
        (start.strftime("%Y-%m-%dT%H:%M:%S"),),
    ).fetchall()
    if len(people) < 2:
        print(f"людей с заказом в окне: {len(people)}")
    ordered = list(reversed(people))
    labels = ("первый", "второй")
    for index, person in enumerate(ordered):
        label = labels[index] if index < len(labels) else str(index + 1)
        rows = conn.execute(
            """
            SELECT created_at, status, purchased, note_charged, task_id,
                   music_provider, plan_json, fail_code,
                   LENGTH(TRIM(COALESCE(lyrics, ''))) AS lyric_len,
                   LENGTH(TRIM(COALESCE(music_url_a, ''))) AS url_a,
                   LENGTH(TRIM(COALESCE(music_url_b, ''))) AS url_b,
                   duration_a, duration_b
            FROM generations
            WHERE (
                CASE
                    WHEN TRIM(COALESCE(user_id, '')) != '' THEN 'u:' || user_id
                    WHEN TRIM(COALESCE(guest_id, '')) != '' THEN 'g:' || guest_id
                    ELSE 'anon'
                END
            ) = ?
              AND created_at >= ?
            ORDER BY created_at
            """,
            (person["who"], start.strftime("%Y-%m-%dT%H:%M:%S")),
        ).fetchall()
        print(f"--- {label}, заказов {len(rows)} ---")
        moments: list[datetime] = []
        for row_index, row in enumerate(rows, start=1):
            moment = parse_utc(row["created_at"])
            if moment:
                moments.append(moment)
            task = "есть" if (row["task_id"] or "").strip() else "нет"
            print(
                f"- {row_index}. {msk(moment)} мск | {stage(row)} | "
                f"{plan_bits(row['plan_json'])} | "
                f"в базе {int(row['lyric_len'] or 0)} знаков | "
                f"задача {task} | цех {row['music_provider'] or '—'} | "
                f"звук {sound(row['url_a'], row['url_b'])} | "
                f"{minutes(row['duration_a'])} и {minutes(row['duration_b'])} | "
                f"нота {'да' if row['note_charged'] else 'нет'} | "
                f"куплена {'да' if row['purchased'] else 'нет'} | "
                f"сбой {fail_label(row['fail_code'])}"
            )
        if not moments:
            print("журнал: времени заказа нет")
            continue
        window_start = min(moments) - timedelta(minutes=20)
        window_end = max(moments) + timedelta(minutes=40)
        found = journal(window_start, window_end)
        print("журнал:")
        if not found:
            print("  строк пути нет")
        else:
            print("\n".join(found))
    print("конец")


if __name__ == "__main__":
    main()
