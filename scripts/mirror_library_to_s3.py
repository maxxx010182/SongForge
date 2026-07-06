#!/usr/bin/env python3
"""Залить готовые треки из БД в S3 REG.RU."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.database.db import get_connection, init_db
from backend.services.storage_service import StorageService


def main() -> None:
    parser = argparse.ArgumentParser(description="Зеркалирование треков в S3")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Все success-генерации, в т.ч. уже storage_synced (перезаливка)",
    )
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--fix", action="store_true", help="Выполнить заливку")
    args = parser.parse_args()

    init_db()
    storage = StorageService()
    print("=== S3 ===")
    print(f"  configured: {storage.enabled()}")
    if not storage.enabled():
        print("  S3 не настроен в .env — см. S3-REG-RU-КАК-ЗАПОЛНИТЬ.txt")
        sys.exit(1)

    query = """
        SELECT id, title, storage_synced
        FROM generations
        WHERE status = 'success'
          AND (music_url_a IS NOT NULL OR music_url_b IS NOT NULL)
    """
    params: list = []
    if not args.all:
        query += " AND storage_synced = 0"
    query += " ORDER BY created_at ASC LIMIT ?"
    params.append(max(1, min(args.limit, 500)))

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    print(f"\n=== Очередь ===")
    print(f"  к заливке: {len(rows)}")
    for row in rows[:10]:
        print(f"  - {row['title'][:40]} | synced={row['storage_synced']}")
    if len(rows) > 10:
        print(f"  ... и ещё {len(rows) - 10}")

    if not args.fix:
        print("\nДля заливки добавьте --fix")
        sys.exit(0)

    ok = 0
    fail = 0
    for row in rows:
        production_id = row["id"]
        if storage.mirror_generation(production_id, force=args.all):
            ok += 1
            print(f"  OK  {production_id[:8]}… {row['title'][:30]}")
        else:
            fail += 1
            print(f"  FAIL {production_id[:8]}… {row['title'][:30]}")

    print(f"\n=== Итог ===")
    print(f"  успех: {ok}, ошибки: {fail}")


if __name__ == "__main__":
    main()