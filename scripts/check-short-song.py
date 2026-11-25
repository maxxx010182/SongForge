#!/usr/bin/env python3
"""Read-only: today's songs, their length, and whether a real lyric was stored.

Does not change songs, money, or the database.
Does not print a name, a mail, a full lyric, a file link, or a key.
"""

from __future__ import annotations

import gzip
import json
import re
import sqlite3
from collections import Counter
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
    r"Music start duration|sunoapi\.org create|APIPass create|Unified lyrics|"
    r"asking the next|LLM \S+/\S+ failed|Lyrics generated|Lyrics attempt|"
    r"All lyrics attempts failed|no text provider",
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


def moscow_midnight_utc() -> str:
    now = datetime.now(timezone.utc) + timedelta(hours=3)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return (start - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")


def clean(text: str, limit: int = 90) -> str:
    flat = " ".join((text or "").split())
    flat = SECRET.sub(r"\1…", flat)
    if len(flat) <= limit:
        return flat or "—"
    return flat[: limit - 1] + "…"


def clock(value) -> str:
    try:
        seconds = int(round(float(value)))
    except (TypeError, ValueError):
        return "—"
    if seconds < 0:
        return "—"
    return f"{seconds // 60}:{seconds % 60:02d}"


def sung_lines(lyrics: str) -> list[str]:
    lines = []
    for raw in (lyrics or "").splitlines():
        text = " ".join(raw.split())
        if not text or text.startswith("["):
            continue
        lines.append(text)
    return lines


def shape(lyrics: str) -> str:
    lower = (lyrics or "").lower()
    body = sung_lines(lyrics)
    marks = []
    verse = lower.count("[verse")
    chorus = lower.count("[chorus")
    if verse:
        marks.append(f"куплет {verse}")
    if chorus:
        marks.append(f"припев {chorus}")
    if "[bridge" in lower:
        marks.append("бридж")
    if not marks:
        marks.append("без меток")
    return f"{', '.join(marks)}, строк {len(body)}"


def repeat_note(lyrics: str) -> str:
    lines = [" ".join(line.lower().split()) for line in sung_lines(lyrics)]
    lines = [line for line in lines if len(line) >= 8]
    if not lines:
        return "поющихся строк нет"
    counts = Counter(lines)
    line, times = counts.most_common(1)[0]
    unique = len(counts)
    return (
        f"разных строк {unique} из {len(lines)}, "
        f"самая частая {times} раз: {clean(line, 50)}"
    )


def same_opening(idea: str, lyrics: str) -> bool:
    left = " ".join((idea or "").lower().split())
    right = " ".join((lyrics or "").lower().split())
    if len(left) < 24 or len(right) < 24:
        return False
    return left[:40] in right or right[:40] in left


def verdict(lyrics: str, idea: str, duration_a, duration_b, asked: int) -> str:
    text = lyrics or ""
    lower = text.lower()
    short_file = False
    for value in (duration_a, duration_b):
        try:
            if float(value) < 150:
                short_file = True
        except (TypeError, ValueError):
            continue
    has_marks = "[verse" in lower or "[chorus" in lower
    no_song = (
        not text.strip()
        or (not has_marks and len(text) < 800)
        or same_opening(idea, text)
    )
    lines = [" ".join(line.lower().split()) for line in sung_lines(text)]
    lines = [line for line in lines if len(line) >= 8]
    looping = False
    if lines:
        _line, times = Counter(lines).most_common(1)[0]
        looping = times >= 3 or len(set(lines)) * 2 < len(lines)
    parts = []
    if no_song:
        parts.append("стих как песня не записан")
    elif looping:
        parts.append("стих есть, строки крутятся")
    else:
        parts.append("стих похож на обычный")
    if short_file:
        asked_note = clock(asked) if asked and asked > 0 else "в плане нет"
        parts.append(f"цех отдал короче 2:30, просили {asked_note}")
    return "; ".join(parts)


def read_tail(path: Path, limit: int = 8000) -> list[str]:
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


def load_rows(conn: sqlite3.Connection, since: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT g.created_at, g.title, g.status, g.purchased, g.note_charged,
               g.duration_a, g.duration_b, g.lyrics, g.style, g.idea,
               g.plan_json, g.fail_msg, g.music_provider, g.music_fallback,
               g.id, g.user_id, u.created_at AS user_at,
               u.trial_generations_used AS trial_used,
               CASE WHEN TRIM(COALESCE(u.email, '')) = '' THEN 0 ELSE 1 END AS has_mail,
               (
                 SELECT provider FROM auth_identities
                 WHERE user_id = g.user_id
                 ORDER BY created_at
                 LIMIT 1
               ) AS provider
        FROM generations g
        LEFT JOIN users u ON u.id = g.user_id
        WHERE g.created_at >= ?
        ORDER BY g.created_at DESC
        LIMIT 8
        """,
        (since,),
    ).fetchall()


def print_row(row: sqlite3.Row) -> None:
    plan = {}
    try:
        plan = json.loads(row["plan_json"] or "{}")
    except json.JSONDecodeError:
        plan = {}
    asked = plan.get("duration_sec") or 0
    lyrics = row["lyrics"] or ""
    idea = row["idea"] or ""
    if row["user_id"]:
        born = "аккаунт сегодня" if msk(row["user_at"])[:5] == msk(row["created_at"])[:5] else "аккаунт старше"
        who = f"{born} | вход {row['provider'] or 'неизвестно'} | почта {'есть' if row['has_mail'] else 'нет'} | пробная {row['trial_used']}"
    else:
        who = "гость, аккаунта нет"
    print(
        f"- {msk(row['created_at'])} мск | {clean(row['title'] or '', 40)} | "
        f"{row['status']} | куплена {row['purchased']} | нота {row['note_charged']}"
    )
    print(f"  кто: {who}")
    print(
        f"  длина A {clock(row['duration_a'])} | B {clock(row['duration_b'])} | "
        f"просили {clock(asked) if asked else '—'} | цех {row['music_provider'] or '—'} | "
        f"запас {row['music_fallback']}"
    )
    print(
        f"  без слов {plan.get('instrumental')} | голос {plan.get('vocal') or '—'}"
    )
    print(f"  слова {len(lyrics)} ({shape(lyrics)})")
    print(f"  повтор: {repeat_note(lyrics)}")
    print(f"  начало слов: {clean(lyrics, 80)}")
    print(f"  идея {len(idea)}: {clean(idea, 80)}")
    print(f"  звучание {len(row['style'] or '')}: {clean(row['style'] or '', 80)}")
    if same_opening(idea, lyrics):
        print("  начало слов совпало с описанием")
    print(f"  итог: {verdict(lyrics, idea, row['duration_a'], row['duration_b'], int(asked or 0))}")
    if row["fail_msg"]:
        print(f"  ошибка {clean(row['fail_msg'], 140)}")


def main() -> None:
    if not DB.is_file():
        print("базы нет")
        return
    since = moscow_midnight_utc()
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = load_rows(conn, since)
    label = "сегодня с полуночи Москвы"
    if not rows:
        since = (
            datetime.now(timezone.utc) - timedelta(hours=36)
        ).strftime("%Y-%m-%dT%H:%M:%S")
        rows = load_rows(conn, since)
        label = "сегодня пусто, вот последние 36 часов"
    print(f"{label}: {len(rows)}")
    needles = []
    titles = []
    for row in rows:
        print_row(row)
        needles.append(row["id"])
        title = " ".join((row["title"] or "").split()).lower()
        if len(title) >= 8:
            titles.append(title[:40])
    print("--- ЖУРНАЛ ---")
    if not needles:
        print("песен за это время нет, журнал не читаю")
        return
    print("Ниже строки про эти песни: писал ли Кие стих и какую длину просили у цеха.")
    shown = 0
    for path in log_files():
        hits = []
        recent: list[str] = []
        follow = 0
        for line in read_tail(path):
            if any(bit in line for bit in SKIP):
                continue
            if not NEEDLE.search(line):
                continue
            recent.append(line)
            if len(recent) > 8:
                recent.pop(0)
            low = line.lower()
            hit = any(item and item in line for item in needles) or any(
                title in low for title in titles
            )
            if hit:
                hits.extend(recent)
                recent = []
                follow = 6
            elif follow:
                hits.append(line)
                follow -= 1
        if not hits:
            continue
        unique = list(dict.fromkeys(hits))
        print(f"{path.name}: строк {len(unique)}")
        for line in unique[-30:]:
            print(clean(line, 220))
            shown += 1
    if shown == 0:
        print("в хвостах журнала нет строк про эти песни")


if __name__ == "__main__":
    main()
