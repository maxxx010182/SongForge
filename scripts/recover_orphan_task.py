#!/usr/bin/env python3
"""Восстановление песни из APIPass, если в БД SongForge нет записи (orphan task)."""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.database.db import get_connection, init_db, utc_now
from backend.models import ProductionPlan
from backend.services.apipass_client import ApiPassClient
from backend.services.cabinet_service import CabinetService
from backend.services.history import HistoryService
from backend.services.storage_service import StorageService


def _find_user_by_email(email: str):
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, email, balance FROM users WHERE LOWER(email) = LOWER(?)",
            (email.strip(),),
        ).fetchone()


def _row_by_task(task_id: str):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM generations WHERE task_id = ?",
            (task_id,),
        ).fetchone()


def _print_apipass(task_id: str) -> dict:
    status = ApiPassClient().get_status(task_id)
    print("=== APIPass ===")
    print(f"  task_id:       {task_id}")
    print(f"  state:         {status.get('state')}")
    print(f"  tracks:        {len(status.get('tracks') or [])}")
    for i, track in enumerate(status.get("tracks") or []):
        url = track.audio_url if hasattr(track, "audio_url") else ""
        print(f"  track[{i}] url: {'есть' if url else 'НЕТ'}")
    return status


def _create_generation_row(
    *,
    production_id: str,
    task_id: str,
    user_id: str,
    title: str,
    note_charged: bool,
) -> None:
    plan = ProductionPlan(
        genre="Pop",
        subgenre="Recovered",
        mood="uplifting",
        explanation_ru="Восстановлено из APIPass",
    )
    HistoryService().attach_task(
        production_id=production_id,
        task_id=task_id,
        idea="Восстановленная генерация",
        title=title,
        lyrics="",
        style="pop",
        plan=plan,
        user_id=user_id,
        guest_id=None,
    )
    if note_charged:
        with get_connection() as conn:
            conn.execute(
                "UPDATE generations SET note_charged = 1 WHERE id = ?",
                (production_id,),
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Восстановить трек из APIPass в БД SongForge"
    )
    parser.add_argument("task_id", help="taskId из панели APIPass")
    parser.add_argument(
        "--email",
        required=True,
        help="Email владельца на сайте (куда положить в фонотеку/историю)",
    )
    parser.add_argument("--title", default="Восстановленная песня", help="Название трека")
    parser.add_argument(
        "--prepaid",
        action="store_true",
        help="Нота была списана при создании (положить в фонотеку)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Записать в БД (без флага — только диагностика)",
    )
    args = parser.parse_args()

    init_db()
    task_id = args.task_id.strip()
    if not task_id:
        print("ОШИБКА: пустой task_id")
        sys.exit(1)

    user = _find_user_by_email(args.email)
    if not user:
        print(f"ОШИБКА: пользователь не найден: {args.email}")
        sys.exit(1)

    try:
        status = _print_apipass(task_id)
    except Exception as exc:
        print(f"ОШИБКА APIPass: {exc}")
        sys.exit(1)

    ap_state = (status.get("state") or "").lower()
    tracks = status.get("tracks") or []
    if ap_state != "success" or not tracks:
        print("\nВосстановление невозможно: APIPass не отдал готовые треки.")
        sys.exit(1)

    row = _row_by_task(task_id)
    print("\n=== SongForge DB ===")
    if row:
        print(f"  production_id: {row['id']}")
        print(f"  status:        {row['status']}")
        print(f"  user_id:       {row['user_id'] or '—'}")
        print(f"  note_charged:  {row['note_charged']}")
        production_id = row["id"]
        orphan = False
    else:
        print("  Записи с этим task_id НЕТ — orphan task.")
        production_id = str(uuid.uuid4())
        orphan = True

    print(f"\n=== План ===")
    print(f"  user:          {user['email']} ({user['id']})")
    print(f"  production_id: {production_id}")
    print(f"  prepaid:       {args.prepaid or bool(row and row['note_charged'])}")

    if not args.fix:
        print("\nДиагностика завершена. Для записи в БД добавьте --fix")
        sys.exit(0)

    history = HistoryService()
    cabinet = CabinetService()
    note_charged = args.prepaid or bool(row and row["note_charged"])

    if orphan:
        _create_generation_row(
            production_id=production_id,
            task_id=task_id,
            user_id=user["id"],
            title=args.title,
            note_charged=note_charged,
        )
        if row is None:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE generations SET created_at = ? WHERE id = ?",
                    (utc_now(), production_id),
                )

    if not orphan and row and row["user_id"] != user["id"]:
        cabinet.link_generation_to_user(
            production_id=production_id,
            user_id=user["id"],
        )

    history.update_task_result(
        task_id=task_id,
        status="success",
        tracks=tracks,
        progress_hint="Восстановлено",
    )

    if note_charged:
        cabinet.complete_prepaid_generation(production_id)
    else:
        with get_connection() as conn:
            conn.execute(
                "UPDATE generations SET purchased = 0 WHERE id = ?",
                (production_id,),
            )

    StorageService().mirror_generation(production_id)

    print("\n=== Готово ===")
    print("  Треки записаны в БД.")
    if note_charged:
        print("  Смотрите: Фонотека → вкладка «Фонотека».")
    else:
        print("  Смотрите: Фонотека → вкладка «История».")
    print("  На сайте: Ctrl+F5")


if __name__ == "__main__":
    main()