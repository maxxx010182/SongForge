#!/usr/bin/env python3
"""Read-only: the last voice try, the text models, and whether a song kept the voice.

Does not change songs, money, or the database.
Does not print a name, a mail, a lyric, a voice number, a file link, or a key.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = Path("/root/SongForge/data/songforge.db")
LOG_DIR = Path("/root/.pm2/logs")
PREFIXES = (
    "songforge-out.log",
    "songforge-error.log",
    "songforge-worker-out.log",
    "songforge-worker-error.log",
)
NEEDLE = re.compile(
    r"LLM \S+/\S+ failed|asking the next|Lyrics generated|All lyrics attempts|"
    r"Music start voice|Music start duration|Music provider|sunoapi\.org task|"
    r"sunoapi\.org create timeout|voice ready|voice failed|voice deleted|"
    r"voice replace|Production ready|no text provider",
    re.I,
)
FAIL_LINE = re.compile(r"LLM \S+/\S+ failed \([^)]+\)")
SECRET = re.compile(
    r"(sk-|key-|Bearer |personaId[\"']?\s*[:=]\s*[\"']?)[A-Za-z0-9_\-]{6,}",
    re.I,
)
EMAIL = re.compile(r"[\w.+\-]+@[\w.\-]+")


def msk(raw: str) -> str:
    text = (raw or "")[:19]
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return text or "?"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (moment.astimezone(timezone.utc) + timedelta(hours=3)).strftime("%d.%m %H:%M")


def since_utc() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=18)).strftime("%Y-%m-%dT%H:%M:%S")


def clock(value) -> str:
    try:
        seconds = int(round(float(value)))
    except (TypeError, ValueError):
        return "—"
    if seconds < 0:
        return "—"
    return f"{seconds // 60}:{seconds % 60:02d}"


def clean(text: str, limit: int = 160) -> str:
    flat = " ".join((text or "").split())
    short = FAIL_LINE.search(flat)
    if short:
        flat = short.group(0)
    flat = SECRET.sub(r"\1…", flat)
    flat = EMAIL.sub("почта", flat)
    if len(flat) <= limit:
        return flat or "—"
    return flat[: limit - 1] + "…"


def voice_flag(plan_json: str) -> str:
    try:
        plan = json.loads(plan_json or "{}")
    except json.JSONDecodeError:
        return "план не читается"
    if (plan.get("own_voice_id") or "").strip():
        return "да"
    return "нет"


def read_tail(path: Path, limit: int = 12000) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        print(f"{path.name}: не открылся ({exc.__class__.__name__})")
        return []
    return lines[-limit:]


def main() -> None:
    if not DB.is_file():
        print("базы нет")
        return
    start = since_utc()
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT g.created_at, g.status, g.purchased, g.note_charged,
               g.duration_a, g.duration_b, g.music_provider, g.music_fallback,
               g.fail_msg, g.plan_json, g.task_id, g.user_id,
               CASE WHEN TRIM(COALESCE(u.email, '')) = '' THEN 0 ELSE 1 END AS has_mail,
               (
                 SELECT provider FROM auth_identities
                 WHERE user_id = g.user_id
                 ORDER BY created_at
                 LIMIT 1
               ) AS login
        FROM generations g
        LEFT JOIN users u ON u.id = g.user_id
        WHERE g.created_at >= ?
        ORDER BY g.created_at
        """,
        (start,),
    ).fetchall()
    print(f"песен за 18 часов: {len(rows)}")
    user_ids = []
    for index, row in enumerate(rows, start=1):
        if row["user_id"]:
            user_ids.append(row["user_id"])
        who = "гость" if not row["user_id"] else (
            f"вход {row['login'] or 'неизвестно'} | почта {'есть' if row['has_mail'] else 'нет'}"
        )
        print(
            f"- {index}. {msk(row['created_at'])} мск | {row['status']} | "
            f"куплена {row['purchased']} | нота {row['note_charged']}"
        )
        print(f"  кто: {who}")
        print(
            f"  длина A {clock(row['duration_a'])} | B {clock(row['duration_b'])} | "
            f"цех {row['music_provider'] or '—'} | запас {row['music_fallback']} | "
            f"задача {'есть' if (row['task_id'] or '').strip() else 'нет'}"
        )
        print(f"  свой голос в песне: {voice_flag(row['plan_json'])}")
        if row["fail_msg"]:
            print(f"  ошибка {clean(row['fail_msg'], 120)}")

    print("--- ГОЛОС НА АККАУНТАХ ЭТИХ ПЕСЕН ---")
    if not user_ids:
        print("аккаунтов нет")
    else:
        marks = ",".join("?" for _ in user_ids)
        voices = conn.execute(
            f"""
            SELECT status, updated_at, fail_msg,
                   CASE WHEN TRIM(COALESCE(voice_id, '')) = '' THEN 0 ELSE 1 END AS has_number,
                   CASE
                     WHEN TRIM(COALESCE(sample_key, '')) = ''
                      AND TRIM(COALESCE(phrase_key, '')) = ''
                     THEN 1 ELSE 0
                   END AS files_gone
            FROM user_voices
            WHERE user_id IN ({marks})
            ORDER BY updated_at
            """,
            user_ids,
        ).fetchall()
        if not voices:
            print("записи голоса нет")
        for voice in voices:
            print(
                f"- {msk(voice['updated_at'])} мск | {voice['status']} | "
                f"номер {'есть' if voice['has_number'] else 'нет'} | "
                f"файлы {'стёрты' if voice['files_gone'] else 'ещё лежат'}"
            )
            if voice["fail_msg"]:
                print(f"  ошибка {clean(voice['fail_msg'], 120)}")

    print("--- ОПЛАТА ЗА 18 ЧАСОВ ---")
    pays = conn.execute(
        """
        SELECT created_at, paid_at, status, package_id, notes_amount
        FROM payment_orders
        WHERE created_at >= ?
        ORDER BY created_at
        """,
        (start,),
    ).fetchall()
    print(f"платежей: {len(pays)}")
    for pay in pays:
        paid = msk(pay["paid_at"]) if pay["paid_at"] else "—"
        print(
            f"- {msk(pay['created_at'])} мск | {pay['status']} | "
            f"{pay['package_id']} | нот {pay['notes_amount']} | оплачен {paid}"
        )

    print("--- ПОДАРКИ ЗА 18 ЧАСОВ ---")
    gifts = conn.execute(
        """
        SELECT created_at, occasion
        FROM gift_links
        WHERE created_at >= ?
        ORDER BY created_at
        """,
        (start,),
    ).fetchall()
    print(f"подарков: {len(gifts)}")
    for gift in gifts:
        print(f"- {msk(gift['created_at'])} мск | повод {gift['occasion'] or '—'}")

    print("--- ЖУРНАЛ ---")
    shown = 0
    if not LOG_DIR.is_dir():
        print("папки журнала нет")
        return
    for path in sorted(LOG_DIR.iterdir()):
        if not path.is_file() or path.name not in PREFIXES:
            continue
        hits = [line for line in read_tail(path) if NEEDLE.search(line)]
        if not hits:
            print(f"{path.name}: пусто")
            continue
        print(f"{path.name}: строк {len(hits)}")
        for line in hits[-40:]:
            print(clean(line, 180))
            shown += 1
    if shown == 0:
        print("в журнале нет строк про текст, голос и цех")


if __name__ == "__main__":
    main()
