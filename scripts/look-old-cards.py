#!/usr/bin/env python3
"""Посмотреть 10 карточек «поделиться» на диске.

Только чтение. В сеть не ходит, публичную ссылку не открывает,
базу и файлы не меняет. Названия и адреса не печатает.
"""

from __future__ import annotations

import io
import sqlite3
import sys
from pathlib import Path

ROOT = Path("/root/SongForge")
if not ROOT.is_dir():
    ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.og_image import build_og_jpeg  # noqa: E402
from backend.settings import DB_PATH, UPLOADS_DIR  # noqa: E402

OLD_HOST = "musicfile.removeai.ai"
# Середина карточки 1200×630, где лежит квадрат обложки.
CENTER = (380, 90, 820, 520)
LOGO_MAX_DIFF = 20
EMPTY_MAX_LIGHT = 22


def _old_ids() -> list[str]:
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, image_url
            FROM user_library
            WHERE published_at IS NOT NULL
              AND TRIM(published_at) != ''
            """
        ).fetchall()
    finally:
        conn.close()
    return [
        row["id"]
        for row in rows
        if OLD_HOST in (row["image_url"] or "")
    ]


def _fallback() -> Path | None:
    for name in ("logo_new.png", "apple-touch-icon.png", "SongForgeLogo.png"):
        path = ROOT / "assets" / name
        if path.is_file():
            return path
    logo = ROOT / "SongForgeLogo.png"
    if logo.is_file():
        return logo
    return None


def _center(image):
    return image.convert("RGB").crop(CENTER)


def _light(image) -> float:
    from PIL import ImageStat

    stat = ImageStat.Stat(image)
    return sum(stat.mean) / len(stat.mean)


def _diff(left, right) -> float:
    from PIL import ImageChops, ImageStat

    stat = ImageStat.Stat(ImageChops.difference(left, right))
    return sum(stat.mean) / len(stat.mean)


def main() -> int:
    from PIL import Image

    fallback = _fallback()
    if fallback is None:
        print("знака сайта на диске нет, сравнить не с чем")
        return 1
    reference = Image.open(io.BytesIO(build_og_jpeg(cover_url="", fallback_path=fallback)))
    mark = _center(reference)
    og_dir = UPLOADS_DIR / "og"
    found = 0
    marks = 0
    pictures = 0
    empty = 0
    scores: list[int] = []
    for library_id in _old_ids():
        path = og_dir / f"{library_id}.jpg"
        if not path.is_file():
            continue
        found += 1
        card = _center(Image.open(path))
        if card.size != mark.size:
            card = card.resize(mark.size)
        score = _diff(card, mark)
        scores.append(round(score))
        if _light(card) <= EMPTY_MAX_LIGHT:
            empty += 1
        elif score <= LOGO_MAX_DIFF:
            marks += 1
        else:
            pictures += 1
    print(f"карточек на диске: {found}")
    print(f"внутри знак сайта: {marks}")
    print(f"внутри другой рисунок: {pictures}")
    print(f"внутри пусто: {empty}")
    if scores:
        print("отличия от знака: " + ", ".join(str(n) for n in sorted(scores)))
    print("файлы не менялись")
    print("база не менялась")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
