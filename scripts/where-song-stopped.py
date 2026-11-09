#!/usr/bin/env python3
"""Только чтение. Где оборвался последний заказ. Текст песни и ключи не печатает."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = Path("/root/SongForge/data/songforge.db")
LOGS = (
    Path("/root/.pm2/logs/songforge-error.log"),
    Path("/root/.pm2/logs/songforge-out.log"),
    Path("/root/.pm2/logs/songforge-worker-error.log"),
    Path("/root/.pm2/logs/songforge-worker-out.log"),
)
SECRET = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._\-]{8,}"
    r"|(?:sk-|apk_|key-)[A-Za-z0-9._\-]{6,}"
    r"|\b(?:api[_-]?key|token|secret|password)\b\s*[=:]\s*\S+"
    r"|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)"
)
LYRIC_LINE = re.compile(r"Production lyrics|preview=|lyrics=")


def msk(raw: str) -> str:
    text = (raw or "")[:19]
    try:
        dt = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    except ValueError:
        return text or "—"
    return (dt + timedelta(hours=3)).strftime("%d.%m %H:%M")


def clean(line: str) -> str:
    flat = " ".join(line.split())
    return SECRET.sub("…", flat)[:220]


def stage(row: sqlite3.Row, library_count: int) -> str:
    status = (row["status"] or "").strip().lower()
    lyrics_len = len(row["lyrics"] or "")
    task = (row["task_id"] or "").strip()
    has_audio = bool((row["music_url_a"] or "").strip() or (row["music_url_b"] or "").strip())
    if status == "success" and has_audio and library_count:
        return "песня готова и есть в фонотеке"
    if status == "success" and has_audio:
        return "песня готова, в фонотеке её нет: она в истории как демо"
    if status == "success":
        return "стоит «готово», но адреса музыки нет"
    if status == "error":
        return "музыкальный цех вернул ошибку, песни нет"
    if status in {"generating", "processing"} and task:
        return "текст уже был, музыка запущена и ответ ещё не записан"
    if lyrics_len and not task:
        return "Кие текст отдал, до музыкального цеха заказ не дошёл"
    if not lyrics_len and not task:
        return "заказ есть, текста ещё нет"
    return f"статус {status or 'пусто'}"


def tail_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - 500_000))
        raw = handle.read(500_000)
    text = raw.decode("utf-8", errors="replace")
    if size > 500_000:
        cut = text.find("\n")
        if cut >= 0:
            text = text[cut + 1 :]
    return text.splitlines()


def main() -> int:
    if not DB.is_file():
        print("базы нет")
        return 1
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cols = {row[1] for row in conn.execute("PRAGMA table_info(generations)")}
    provider = "music_provider" if "music_provider" in cols else "'' AS music_provider"
    fail_code = "fail_code" if "fail_code" in cols else "'' AS fail_code"
    user = conn.execute(
        """
        SELECT id, display_name, created_at, trial_generations_used
        FROM users
        ORDER BY created_at DESC
        LIMIT 1
        """
    ).fetchone()
    if not user:
        print("пользователей нет")
        return 0
    print(
        f"последний человек: {(user['display_name'] or 'без имени').strip()[:40]} | "
        f"зарегистрирован {msk(user['created_at'])} мск | "
        f"проба {'была' if user['trial_generations_used'] else 'не было'}"
    )
    rows = conn.execute(
        f"""
        SELECT id, created_at, title, status, task_id, lyrics, fail_msg,
               music_url_a, music_url_b, purchased, note_charged,
               {provider}, {fail_code}
        FROM generations
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 3
        """,
        (user["id"],),
    ).fetchall()
    print(f"его заказов в базе, последних: {len(rows)}")
    if not rows:
        print("этап: человек есть, заказа песни в базе нет. Кие мог ответить, а запись у нас не сохранилась.")
        return 0
    newest = rows[0]
    for row in rows:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM user_library WHERE generation_id = ?",
            (row["id"],),
        ).fetchone()["c"]
        print(
            f"- {msk(row['created_at'])} мск | {str(row['title'] or 'без названия')[:40]} | "
            f"{stage(row, int(count))} | цех {row['music_provider'] or '—'} | "
            f"текст {len(row['lyrics'] or '')} знаков | "
            f"задача {'есть' if (row['task_id'] or '').strip() else 'нет'} | "
            f"нота {int(row['note_charged'] or 0)} | куплена {int(row['purchased'] or 0)}"
        )
        if (row["fail_code"] or "").strip() or (row["fail_msg"] or "").strip():
            print(f"  сбой {clean(str(row['fail_code'] or ''))} {clean(str(row['fail_msg'] or ''))}")
    print(f"этап последнего: {stage(newest, int(conn.execute('SELECT COUNT(*) AS c FROM user_library WHERE generation_id = ?', (newest['id'],)).fetchone()['c']))}")
    needles = [newest["id"]]
    task = (newest["task_id"] or "").strip()
    if task:
        needles.append(task)
    print("--- журнал по этому заказу ---")
    shown = 0
    for path in LOGS:
        lines = [
            line
            for line in tail_lines(path)
            if any(needle in line for needle in needles) and not LYRIC_LINE.search(line)
        ]
        print(f"{path.name}: строк {len(lines)}")
        for line in lines[-8:]:
            print(clean(line))
            shown += 1
    if shown == 0:
        print("в хвосте журнала этого заказа нет")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
