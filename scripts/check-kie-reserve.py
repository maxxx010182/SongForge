#!/usr/bin/env python3
"""Read-only: after the last Kie errors, was the next text model asked?

Does not change songs, money, or the database. Does not print lyrics or keys.
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
    r"LLM Kie/|LLM ApiPass/|Kie/\S+ response received|Kie \S+ HTTP |"
    r"Unified package stopped|Unified package kept|no text provider|"
    r"Lyrics generated via|All lyrics attempts failed|asking the next",
    re.I,
)
SECRET = re.compile(r"(sk-|key-|Bearer )[A-Za-z0-9_\-]{8,}")
FAIL = re.compile(r"LLM (\S+)/(\S+) failed \(([^)]+)\)")
HTTP = re.compile(r"Kie (\S+) HTTP (\d+)")
OK = re.compile(r"Kie/(\S+) response received \((\d+) chars\)")
NEXT = re.compile(r"LLM (\S+)/(\S+) no text after (\d+)s")
SKIP_LINE = "LLM provider:"


def msk(raw: str) -> str:
    text = (raw or "")[:19]
    try:
        dt = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    except ValueError:
        return text or "?"
    return (dt + timedelta(hours=3)).strftime("%d.%m %H:%M:%S")


def stamp(line: str) -> datetime | None:
    text = (line or "")[:19]
    try:
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def clean(line: str) -> str:
    flat = " ".join(line.split())
    return SECRET.sub(r"\1…", flat)[:220]


def log_files() -> list[Path]:
    if not LOG_DIR.is_dir():
        return []
    found: list[Path] = []
    for path in LOG_DIR.iterdir():
        if not path.is_file():
            continue
        if not path.name.startswith(PREFIXES):
            continue
        found.append(path)
    return sorted(found, key=lambda item: item.stat().st_mtime)


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


def hits_of(path: Path) -> list[str]:
    rows = []
    for line in read_tail(path):
        if SKIP_LINE in line or "provider balance kie" in line:
            continue
        if "Kie credits check failed" in line:
            continue
        if NEEDLE.search(line):
            rows.append(line)
    return rows


def model_of(line: str) -> str:
    for pattern in (FAIL, HTTP, OK, NEXT):
        found = pattern.search(line)
        if not found:
            continue
        if pattern is FAIL or pattern is NEXT:
            return found.group(2)
        return found.group(1)
    if "ApiPass" in line:
        return "ApiPass"
    return ""


def kind_of(line: str) -> str:
    failed = FAIL.search(line)
    if failed:
        return failed.group(3)
    if HTTP.search(line):
        return "http"
    if OK.search(line):
        return "text"
    if NEXT.search(line):
        return "timeout"
    if "stopped" in line or "All lyrics attempts failed" in line or "no text provider" in line:
        return "stop"
    return "note"


def burst(lines: list[str]) -> list[str]:
    """Last run of text-model lines. A gap over 10 minutes starts a new run."""
    if not lines:
        return []
    chosen = [lines[-1]]
    previous = stamp(lines[-1])
    for line in reversed(lines[:-1]):
        current = stamp(line)
        if previous and current and previous - current > timedelta(minutes=10):
            break
        chosen.append(line)
        if current:
            previous = current
        if len(chosen) >= 24:
            break
    chosen.reverse()
    return chosen


def explain(lines: list[str]) -> None:
    if not lines:
        print("разбор: в журнале нет строк про очередь текста")
        return
    models: list[str] = []
    kinds: dict[str, list[str]] = {}
    http_count: dict[str, int] = {}
    for line in lines:
        name = model_of(line)
        kind = kind_of(line)
        if name and name not in models and kind in {"http", "text", "timeout", "gone", "maintenance", "other"}:
            models.append(name)
        if name:
            kinds.setdefault(name, [])
            if kind not in kinds[name]:
                kinds[name].append(kind)
        found = HTTP.search(line)
        if found:
            http_count[found.group(1)] = http_count.get(found.group(1), 0) + 1
    print("разбор последней пачки:")
    for name, count in http_count.items():
        if count >= 2:
            print(
                f"- {name}: строк HTTP {count}. "
                "Это повтор того же запроса, не следующая модель."
            )
    called = [name for name in models if any(k != "note" for k in kinds.get(name, []))]
    if len(called) >= 2:
        print("- очередь дошла до следующей модели: " + ", ".join(called))
        return
    if len(called) == 1:
        only = called[0]
        only_kinds = ", ".join(kinds.get(only, []))
        print(f"- в пачке только {only} ({only_kinds})")
        print("- строки следующей модели в этой пачке нет")
        return
    print("- по этим строкам модель не разобрать, смотри список выше")


def main() -> None:
    print("заказы:")
    if not DB.is_file():
        print("- базы на этом компьютере нет")
    else:
        conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT created_at, title, status, purchased, fail_msg
            FROM generations
            ORDER BY created_at DESC
            LIMIT 6
            """
        ).fetchall()
        if not rows:
            print("- заказов нет")
        for row in rows:
            err = clean(row["fail_msg"]) if row["fail_msg"] else ""
            print(
                f"- {msk(row['created_at'])} мск | {str(row['title'] or '')[:40]} | "
                f"{row['status']} | куплена {row['purchased']}"
                + (f" | {err}" if err else "")
            )
    print("--- журнал ---")
    files = log_files()
    if not files:
        print("папки журнала нет")
        return
    collected: list[str] = []
    for path in files:
        found = hits_of(path)
        print(f"{path.name}: строк {len(found)}")
        collected.extend(found)
    collected.sort(key=lambda line: line[:23])
    if not collected:
        print("строк про очередь текста нет")
        return
    last = burst(collected)
    print("--- последняя пачка ---")
    for line in last:
        moment = msk(line)
        print(f"{moment} мск | {clean(line)[23:].strip()}")
    explain(last)


if __name__ == "__main__":
    main()
