#!/usr/bin/env python3
"""Read-only: today's Kie failures. Skips the startup line."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = Path("/root/SongForge/data/songforge.db")
LOGS = [
    Path("/root/.pm2/logs/songforge-out.log"),
    Path("/root/.pm2/logs/songforge-error.log"),
    Path("/root/.pm2/logs/songforge-worker-out.log"),
    Path("/root/.pm2/logs/songforge-worker-error.log"),
]
NEEDLE = re.compile(
    r"failed \(|asking the next|LlmUnavailable|Unified |Production ready|"
    r"ReadTimeout|ConnectTimeout|error 40[12]|status[=: ]40[12]|\bno text\b",
    re.I,
)
SKIP = "LLM provider:"
SECRET = re.compile(r"(sk-|key-|Bearer )[A-Za-z0-9_\-]{8,}")


def msk(raw: str) -> str:
    text = (raw or "")[:19]
    try:
        dt = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    except ValueError:
        return text
    return (dt + timedelta(hours=3)).strftime("%d.%m %H:%M")


def clean(line: str) -> str:
    flat = " ".join(line.split())
    return SECRET.sub(r"\1…", flat)[:240]


def tail(path: Path, limit: int = 12000) -> list[str]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT created_at, title, status, purchased, fail_msg
        FROM generations
        WHERE created_at >= datetime('now', '-2 day')
        ORDER BY created_at DESC
        LIMIT 8
        """
    ).fetchall()
    print(f"заказов за 2 дня: {len(rows)}")
    for row in rows:
        err = clean(row["fail_msg"]) if row["fail_msg"] else ""
        print(
            f"- {msk(row['created_at'])} мск | {str(row['title'] or '')[:40]} | "
            f"{row['status']} | куплена {row['purchased']}"
            + (f" | {err}" if err else "")
        )
    print("--- KIE ---")
    shown = 0
    for path in LOGS:
        lines = tail(path)
        if not lines:
            print(f"{path.name}: нет файла")
            continue
        starts = [line for line in lines if SKIP in line]
        hits = [line for line in lines if NEEDLE.search(line) and SKIP not in line]
        print(f"{path.name}: запусков {len(starts)}, строк про сбой {len(hits)}")
        if starts:
            print(f"  первый запуск {starts[0][:19]} utc, последний {starts[-1][:19]} utc")
        for line in hits[-40:]:
            print(clean(line))
            shown += 1
    if shown == 0:
        print("в хвостах журналов нет строк про сбой Кие")


if __name__ == "__main__":
    main()
