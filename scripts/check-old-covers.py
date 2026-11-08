#!/usr/bin/env python3
"""Проверить, открывается ли старая обложка с сервера.

Только чтение. Базу, площадку и файлы не меняет.
Названия и адреса не печатает.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import requests

ROOT = Path("/root/SongForge")
if not ROOT.is_dir():
    ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.storage_service import image_kind  # noqa: E402
from backend.settings import DB_PATH, UPLOADS_DIR  # noqa: E402

OLD_HOST = "musicfile.removeai.ai"
TRY_COUNT = 3
CONNECT_SEC = 8
READ_SEC = 12


def _rows() -> list[sqlite3.Row]:
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        return list(
            conn.execute(
                """
                SELECT id, image_url
                FROM user_library
                WHERE published_at IS NOT NULL
                  AND TRIM(published_at) != ''
                """
            )
        )
    finally:
        conn.close()


def _probe(url: str) -> str:
    try:
        response = requests.get(
            url,
            timeout=(CONNECT_SEC, READ_SEC),
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "image/*,*/*",
            },
        )
    except requests.RequestException:
        return "не открылась"
    data = response.content or b""
    if response.status_code >= 400 or not data:
        return "не открылась"
    kind = image_kind(data)
    if kind is None:
        return f"ответ есть, это не картинка, {len(data)} байт"
    return f"открылась картинка, {kind[1]}, {len(data)} байт"


def main() -> int:
    rows = _rows()
    old = [
        row
        for row in rows
        if OLD_HOST in (row["image_url"] or "")
    ]
    ours = [
        row
        for row in rows
        if "s3.regru.cloud" in (row["image_url"] or "")
        or "/tracks/" in (row["image_url"] or "")
    ]
    empty = [row for row in rows if not (row["image_url"] or "").strip()]
    other = len(rows) - len(old) - len(ours) - len(empty)
    og_dir = UPLOADS_DIR / "og"
    sizes: list[int] = []
    for row in old:
        path = og_dir / f"{row['id']}.jpg"
        if path.is_file():
            sizes.append(path.stat().st_size)
    print(f"на площадке песен: {len(rows)}")
    print(f"со старым адресом: {len(old)}")
    print(f"уже в нашем хранилище: {len(ours)}")
    print(f"пустой адрес: {len(empty)}")
    print(f"другой адрес: {other}")
    sample = old[:TRY_COUNT]
    print(f"проверено адресов с сервера: {len(sample)}")
    opened = 0
    for row in sample:
        line = _probe((row["image_url"] or "").strip())
        if line.startswith("открылась"):
            opened += 1
        print(line)
    print(f"открылось: {opened}")
    print(f"карточек «поделиться» на диске: {len(sizes)} из {len(old)}")
    if sizes:
        print(f"меньшая карточка: {min(sizes)} байт")
        print(f"большая карточка: {max(sizes)} байт")
    print("база не менялась")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
