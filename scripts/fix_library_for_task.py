#!/usr/bin/env python3
"""Положить треки в фонотеку, если generations.purchased=1, а user_library пуст."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.database.db import init_db
from backend.services.cabinet_service import CabinetService


def _user_by_email(email: str):
    from backend.database.db import get_connection

    with get_connection() as conn:
        return conn.execute(
            "SELECT id, email FROM users WHERE LOWER(email) = LOWER(?)",
            (email.strip(),),
        ).fetchone()


def _gen_by_task(task_id: str):
    from backend.database.db import get_connection

    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM generations WHERE task_id = ?",
            (task_id.strip(),),
        ).fetchone()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Дописать user_library для готовой генерации"
    )
    parser.add_argument("task_id")
    parser.add_argument("--email", required=True)
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args()

    init_db()
    gen = _gen_by_task(args.task_id)
    if not gen:
        print("ОШИБКА: генерация не найдена")
        sys.exit(1)

    user = _user_by_email(args.email)
    if not user:
        print(f"ОШИБКА: пользователь не найден: {args.email}")
        sys.exit(1)

    cabinet = CabinetService()
    lib_count = cabinet.library_entry_count(gen["id"])

    print("=== Диагностика ===")
    print(f"  task_id:       {args.task_id}")
    print(f"  production_id: {gen['id']}")
    print(f"  title:         {gen['title']}")
    print(f"  status:        {gen['status']}")
    print(f"  gen user_id:   {gen['user_id'] or '—'}")
    print(f"  ваш user_id:   {user['id']}")
    print(f"  purchased:     {gen['purchased']}")
    print(f"  note_charged:  {gen['note_charged']}")
    print(f"  в фонотеке:    {lib_count} записей")

    if gen["user_id"] != user["id"]:
        print("\n  ВНИМАНИЕ: песня привязана к другому user_id — при --fix перепривяжем.")

    if lib_count >= 2:
        print("\n  Уже в фонотеке. Ctrl+F5 на сайте.")
        sys.exit(0)

    if not args.fix:
        print("\nДля записи в фонотеку добавьте --fix")
        sys.exit(0)

    if gen["user_id"] != user["id"]:
        cabinet.link_generation_to_user(
            production_id=gen["id"],
            user_id=user["id"],
        )

    ok = cabinet.ensure_library_from_generation(gen["id"])
    if not ok:
        ok = cabinet.complete_prepaid_generation(gen["id"])

    lib_after = cabinet.library_entry_count(gen["id"])
    print("\n=== Готово ===")
    print(f"  записей в фонотеке: {lib_after}")
    if lib_after > 0:
        print("  Сайт: Ctrl+F5 → Фонотека → вкладка «Фонотека»")
    else:
        print("  Не удалось записать — пришлите этот вывод в чат.")


if __name__ == "__main__":
    main()