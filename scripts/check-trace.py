#!/usr/bin/env python3
"""Read-only: last traceback blocks. Secrets are cut. Does not change the site."""

from __future__ import annotations

import re
from pathlib import Path

LOGS = (
    ("/root/.pm2/logs/songforge-error.log", "ошибки сайта"),
    ("/root/.pm2/logs/songforge-worker-error.log", "ошибки воркера"),
)
SECRET = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._\-]{8,}"
    r"|(?:sk-|apk_|key-)[A-Za-z0-9._\-]{6,}"
    r"|\b(?:api[_-]?key|token|secret|password)\b\s*[=:]\s*\S+"
    r"|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)"
)


def clean(line: str) -> str:
    flat = " ".join(line.split())
    return SECRET.sub("…", flat)[:220]


def tail(path: Path) -> list[str]:
    if not path.is_file():
        return []
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - 400_000))
        raw = handle.read(400_000)
    text = raw.decode("utf-8", errors="replace")
    if size > 400_000:
        cut = text.find("\n")
        if cut >= 0:
            text = text[cut + 1 :]
    return text.splitlines()


def main() -> None:
    for name, label in LOGS:
        lines = tail(Path(name))
        starts = [i for i, line in enumerate(lines) if "Traceback (most recent call last)" in line]
        print(f"--- {label}: следов {len(starts)} ---")
        if not lines:
            print("файла нет")
            continue
        for begin in starts[-2:]:
            print(f"след со строки {begin}")
            chunk = lines[begin : begin + 18]
            for line in chunk:
                print(clean(line))
            print()
        if not starts:
            print("слова Traceback в хвосте нет")


if __name__ == "__main__":
    main()
