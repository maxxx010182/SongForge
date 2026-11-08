#!/usr/bin/env python3
"""Поставить готовые обложки песням, у которых на площадке знак сайта.

Чужие живые картинки не трогает. Названия и адреса не печатает.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path("/root/SongForge")
if not ROOT.is_dir():
    ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database.db import get_connection  # noqa: E402
from backend.services.storage_service import StorageService, image_kind  # noqa: E402
from backend.settings import S3_BUCKET  # noqa: E402

OLD_HOST = "musicfile.removeai.ai"
SAFE_ID = re.compile(r"^[a-fA-F0-9-]{8,64}$")


def _needs_cover(url: str) -> bool:
    raw = (url or "").strip()
    if not raw:
        return True
    return OLD_HOST in raw


def _store(storage: StorageService, generation_id: str, variant: str, data: bytes) -> str:
    kind = image_kind(data)
    if kind is None:
        raise RuntimeError("not an image")
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


def _write(storage: StorageService, generation_id: str, variant: str, public: str) -> None:
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
        urls = (
            (row["image_url_a"] if row else "") or "",
            (row["image_url_b"] if row else "") or "",
        )
        foreign = [url for url in urls if url.strip() and not storage.is_our_storage_url(url)]
        if row and not foreign:
            conn.execute(
                "UPDATE generations SET cover_synced = 1 WHERE id = ?",
                (generation_id,),
            )


def main() -> int:
    storage = StorageService()
    if not storage.enabled():
        print("хранилище выключено")
        return 1
    folder = ROOT / "scripts" / "showcase-covers"
    mapping = json.loads((folder / "map.json").read_text(encoding="utf-8"))
    saved = 0
    already = 0
    skipped = 0
    for library_id, filename in mapping.items():
        if not SAFE_ID.match(library_id) or "/" in filename or ".." in filename:
            skipped += 1
            continue
        path = folder / filename
        if not path.is_file():
            skipped += 1
            continue
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT generation_id, variant, image_url
                FROM user_library
                WHERE id = ?
                """,
                (library_id,),
            ).fetchone()
        if not row:
            skipped += 1
            continue
        if not _needs_cover(row["image_url"] or ""):
            already += 1
            continue
        variant = (row["variant"] or "").strip().upper()
        generation_id = storage._safe_track_id(row["generation_id"] or "")
        if variant not in ("A", "B") or not generation_id:
            skipped += 1
            continue
        data = path.read_bytes()
        if image_kind(data) is None or len(data) < 500:
            skipped += 1
            continue
        public = _store(storage, generation_id, variant, data)
        _write(storage, generation_id, variant, public)
        saved += 1
    print(f"поставлено обложек: {saved}")
    print(f"уже были свои: {already}")
    print(f"пропущено: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
