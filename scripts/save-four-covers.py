#!/usr/bin/env python3
"""Сохранить 4 найденных рисунка к своим песням на площадке.

Берёт только карточки, где середина не совпадает со знаком сайта.
Остальные песни не трогает. Названия и адреса не печатает.
"""

from __future__ import annotations

import io
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path("/root/SongForge")
if not ROOT.is_dir():
    ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database.db import get_connection  # noqa: E402
from backend.og_image import build_og_jpeg  # noqa: E402
from backend.services.storage_service import StorageService, image_kind  # noqa: E402
from backend.settings import DB_PATH, S3_BUCKET, UPLOADS_DIR  # noqa: E402

OLD_HOST = "musicfile.removeai.ai"
CENTER = (380, 90, 820, 520)
PICTURE_MIN_DIFF = 30
CURRENT_PROVIDER = "sunoapi"


def _published() -> list[sqlite3.Row]:
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        return list(
            conn.execute(
                """
                SELECT ul.id, ul.generation_id, ul.variant, ul.image_url,
                       COALESCE(g.task_id, '') AS task_id,
                       COALESCE(g.music_provider, '') AS music_provider
                FROM user_library ul
                LEFT JOIN generations g ON g.id = ul.generation_id
                WHERE ul.published_at IS NOT NULL
                  AND TRIM(ul.published_at) != ''
                """
            )
        )
    finally:
        conn.close()


def _fallback() -> Path | None:
    for name in ("logo_new.png", "apple-touch-icon.png"):
        path = ROOT / "assets" / name
        if path.is_file():
            return path
    return None


def _diff(card, mark) -> float:
    from PIL import ImageChops, ImageStat

    piece = card.convert("RGB").crop(CENTER)
    if piece.size != mark.size:
        piece = piece.resize(mark.size)
    stat = ImageStat.Stat(ImageChops.difference(piece, mark))
    return sum(stat.mean) / len(stat.mean)


def _is_margin(rgb: tuple[int, int, int]) -> bool:
    red, green, blue = rgb
    return max(red, green, blue) < 40 and abs(red - green) < 18 and abs(green - blue) < 18


def _cover_box(image) -> tuple[int, int, int, int] | None:
    """Квадрат рисунка внутри широкой карточки. Рамка в квадрат не входит."""
    rgb = image.convert("RGB")
    pix = rgb.load()
    width, height = rgb.size
    if width < 900 or height < 500:
        return None
    xs: list[int] = []
    ys: list[int] = []
    for y in (220, 300, 380):
        left = width // 2
        while left > 200 and not _is_margin(pix[left, y]):
            left -= 1
        right = width // 2
        while right < width - 200 and not _is_margin(pix[right, y]):
            right += 1
        xs.extend((left + 1, right - 1))
    for x in (520, 600, 680):
        top = height // 2
        while top > 40 and not _is_margin(pix[x, top]):
            top -= 1
        bottom = height // 2
        while bottom < height - 70 and not _is_margin(pix[x, bottom]):
            bottom += 1
        ys.extend((top + 1, bottom - 1))
    box = (min(xs) + 4, min(ys) + 4, max(xs) - 3, max(ys) - 3)
    if box[2] - box[0] < 80 or box[3] - box[1] < 80:
        return None
    if box[2] - box[0] > 520 or box[3] - box[1] > 520:
        return None
    return box


def _jpeg(image) -> bytes:
    out = io.BytesIO()
    image.convert("RGB").save(out, format="JPEG", quality=90, optimize=True)
    return out.getvalue()


def _store(storage: StorageService, generation_id: str, variant: str, data: bytes) -> str:
    kind = image_kind(data)
    if kind is None:
        raise RuntimeError("crop is not an image")
    content_type, ext = kind
    key = f"tracks/{generation_id}/{variant.lower()}-cover.{ext}"
    client = storage._get_client()
    client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return storage.public_url(key)


def _remember_once(
    storage: StorageService,
    generation_id: str,
    variant: str,
    public: str,
) -> None:
    with get_connection() as conn:
        if variant == "A":
            conn.execute(
                "UPDATE generations SET image_url_a = ? WHERE id = ?",
                (public, generation_id),
            )
        else:
            conn.execute(
                "UPDATE generations SET image_url_b = ? WHERE id = ?",
                (public, generation_id),
            )
        conn.execute(
            """
            UPDATE user_library
            SET image_url = ?
            WHERE generation_id = ? AND UPPER(variant) = ?
            """,
            (public, generation_id, variant),
        )
        row = conn.execute(
            "SELECT image_url_a, image_url_b FROM generations WHERE id = ?",
            (generation_id,),
        ).fetchone()
        urls = ((row["image_url_a"] if row else ""), (row["image_url_b"] if row else ""))
        foreign = [
            url
            for url in urls
            if (url or "").strip() and not storage.is_our_storage_url(url)
        ]
        if row and not foreign:
            conn.execute(
                "UPDATE generations SET cover_synced = 1 WHERE id = ?",
                (generation_id,),
            )


def _remember(
    storage: StorageService,
    generation_id: str,
    variant: str,
    public: str,
) -> None:
    for attempt in range(5):
        try:
            _remember_once(storage, generation_id, variant, public)
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 4:
                raise
            time.sleep(2)


def main() -> int:
    from PIL import Image

    print("скрипт 2")
    storage = StorageService()
    if not storage.enabled():
        print("хранилище выключено")
        return 1
    fallback = _fallback()
    if fallback is None:
        print("знака сайта на диске нет")
        return 1
    mark = Image.open(io.BytesIO(build_og_jpeg(cover_url="", fallback_path=fallback))).crop(CENTER)
    og_dir = UPLOADS_DIR / "og"
    saved = 0
    skipped = 0
    for row in _published():
        url = (row["image_url"] or "").strip()
        if OLD_HOST not in url:
            continue
        path = og_dir / f"{row['id']}.jpg"
        if not path.is_file():
            continue
        card = Image.open(path)
        if _diff(card, mark) <= PICTURE_MIN_DIFF:
            continue
        variant = (row["variant"] or "").strip().upper()
        generation_id = storage._safe_track_id(row["generation_id"] or "")
        box = _cover_box(card)
        if variant not in ("A", "B") or not generation_id or box is None:
            skipped += 1
            continue
        data = _jpeg(card.crop(box))
        if image_kind(data) is None or len(data) < 500:
            skipped += 1
            continue
        public = _store(storage, generation_id, variant, data)
        _remember(storage, generation_id, variant, public)
        saved += 1
    old_left = [
        row
        for row in _published()
        if OLD_HOST in (row["image_url"] or "")
    ]
    with_task = [row for row in old_left if (row["task_id"] or "").strip()]
    same = [row for row in with_task if (row["music_provider"] or "") == CURRENT_PROVIDER]
    print(f"сохранено к песням: {saved}")
    print(f"не удалось вырезать: {skipped}")
    print(f"осталось без рисунка: {len(old_left)}")
    print(f"у них есть номер задачи: {len(with_task)}")
    print(f"номера нет: {len(old_left) - len(with_task)}")
    print(f"номер от текущего цеха: {len(same)}")
    print(f"номер от прежнего цеха: {len(with_task) - len(same)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
