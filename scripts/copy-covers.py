#!/usr/bin/env python3
"""Забрать обложки в наше хранилище.

Живую картинку копирует. Адрес, который не открылся, не стирает.
Песни не удаляет. Названия и ссылки не печатает.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/root/SongForge")
if not ROOT.is_dir():
    ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.storage_service import StorageService  # noqa: E402


def main() -> int:
    storage = StorageService()
    if not storage.enabled():
        print("хранилище выключено")
        return 1
    songs = storage.list_cover_song_ids()
    saved = 0
    cleared = 0
    for song_id in songs:
        first = storage.copy_covers(song_id)
        saved += first.saved
        if first.state == "failed":
            second = storage.copy_covers(song_id, give_up=True)
            saved += second.saved
            cleared += second.cleared
    print(f"песен проверено: {len(songs)}")
    print(f"обложек сохранено: {saved}")
    print(f"обложек больше нет, на карточке знак сайта: {cleared}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
