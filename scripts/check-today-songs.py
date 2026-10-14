#!/usr/bin/env python3
"""Read-only: songs and payments since midnight Moscow on 14 Oct 2026, plus matching log lines."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

DB = Path("/root/SongForge/data/songforge.db")
LOGS = [
    Path("/root/.pm2/logs/songforge-out.log"),
    Path("/root/.pm2/logs/songforge-error.log"),
    Path("/root/.pm2/logs/songforge-worker-out.log"),
    Path("/root/.pm2/logs/songforge-worker-error.log"),
]
# 14 Oct 2026 00:00 Moscow = 13 Oct 21:00 UTC
SINCE = "2026-10-13T21:00:00"
MARKERS = (
    "Production ready",
    "Production lyrics",
    "Kie/",
    "asking the next",
    "Unified package",
    "APIPass",
    "sunoapi.org",
    "S3 mirror",
    "GetPlatinum",
    "Music provider",
    "ERROR",
    "Exception",
    "Traceback",
)


def host_of(url: str) -> str:
    if not url:
        return "-"
    try:
        return urlparse(url).netloc or "-"
    except Exception:
        return "-"


def one_line(text: str, limit: int = 90) -> str:
    flat = " ".join((text or "").split())
    return flat[:limit]


def tail(path: Path, limit: int = 6000) -> list[str]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]


def main() -> None:
    if not DB.is_file():
        print(f"базы нет: {DB}")
        return
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, substr(created_at,1,19) AS at, status, title, purchased,
               note_charged, duration_a, duration_b, task_id, fail_msg,
               lyrics, style, idea, plan_json, music_url_a, music_url_b
        FROM generations
        WHERE created_at >= ?
        ORDER BY created_at
        """,
        (SINCE,),
    ).fetchall()
    print(f"песен с полуночи Москвы 14.10: {len(rows)}")
    needles: list[str] = []
    for row in rows:
        plan = {}
        try:
            plan = json.loads(row["plan_json"] or "{}")
        except json.JSONDecodeError:
            plan = {}
        lib = conn.execute(
            "SELECT COUNT(*) AS n FROM user_library WHERE generation_id = ?",
            (row["id"],),
        ).fetchone()["n"]
        print(
            f"- {row['at']} | {one_line(row['title'] or '', 40)} | {row['status']} | "
            f"куплена {row['purchased']} | нота {row['note_charged']} | в фонотеке {lib}"
        )
        print(
            f"  длина A {row['duration_a']} B {row['duration_b']} | "
            f"текст {len(row['lyrics'] or '')} | стиль {len(row['style'] or '')} | "
            f"без слов {plan.get('instrumental')} | запрос {plan.get('duration_sec')}"
        )
        print(
            f"  файл A {host_of(row['music_url_a'] or '')} | "
            f"файл B {host_of(row['music_url_b'] or '')}"
        )
        if row["fail_msg"]:
            print(f"  ошибка {one_line(row['fail_msg'], 140)}")
        print(f"  идея {one_line(row['idea'] or '', 100)}")
        needles.append(str(row["id"]))
        if row["task_id"]:
            needles.append(str(row["task_id"])[:16])

    pays = conn.execute(
        """
        SELECT substr(created_at,1,19) AS at, substr(COALESCE(paid_at,''),1,19) AS paid,
               status, package_id, notes_amount, price_rub
        FROM payment_orders
        WHERE created_at >= ? OR COALESCE(paid_at,'') >= ?
        ORDER BY created_at
        """,
        (SINCE, SINCE),
    ).fetchall()
    print(f"оплат за это время: {len(pays)}")
    for pay in pays:
        print(
            f"- {pay['at']} | {pay['status']} | {pay['package_id']} | "
            f"{pay['notes_amount']} нот | {pay['price_rub']} руб | оплачено {pay['paid'] or '-'}"
        )

    print("--- LOG ---")
    shown = 0
    for path in LOGS:
        lines = tail(path)
        if not lines:
            print(f"{path.name}: нет файла")
            continue
        hit = []
        for line in lines:
            if any(n and n in line for n in needles) or any(m in line for m in MARKERS):
                if "2026-10-13T2" in line or "2026-10-14" in line or "2026-10-13 2" in line:
                    hit.append(line)
                elif any(n and n in line for n in needles):
                    hit.append(line)
        print(f"{path.name}: подходящих строк {len(hit)}")
        for line in hit[-40:]:
            print(one_line(line, 220))
            shown += 1
    if shown == 0:
        print("в хвостах журналов нет строк про эти песни")


if __name__ == "__main__":
    main()
