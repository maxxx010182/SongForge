#!/usr/bin/env python3
"""Проверка одной генерации: БД SongForge ↔ APIPass."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.database.db import get_connection, init_db
from backend.services.music_provider_service import MusicProviderService
from backend.services.history import HistoryService


def main() -> None:
    if len(sys.argv) < 2:
        print("Использование: python scripts/check_task.py <task_id>")
        print("Или:          python scripts/check_task.py last")
        print("Восстановить: python scripts/check_task.py last --fix")
        sys.exit(1)

    do_fix = "--fix" in sys.argv

    init_db()
    task_id = sys.argv[1]

    with get_connection() as conn:
        if task_id == "last":
            row = conn.execute(
                """
                SELECT * FROM generations
                WHERE task_id IS NOT NULL AND task_id != ''
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM generations WHERE task_id = ?",
                (task_id,),
            ).fetchone()

    if not row:
        if task_id == "last":
            print("В БД нет ни одной генерации с task_id.")
            sys.exit(1)
        print("=== SongForge DB ===")
        print("  Записи с этим task_id НЕТ (orphan task).")
        print("\n=== Music API recordInfo ===")
        try:
            status = MusicProviderService().get_status(task_id)
        except Exception as exc:
            print(f"  ОШИБКА запроса music API: {exc}")
            sys.exit(1)
        print(f"  state:         {status['state']}")
        print(f"  tracks parsed: {len(status.get('tracks') or [])}")
        ap_state = (status["state"] or "").lower()
        print("\n=== Диагноз ===")
        if ap_state == "success" and status.get("tracks"):
            print(
                "  APIPass готов, но SongForge не сохранил задачу.\n"
                "  Восстановление: scripts/recover_orphan_task.py (см. ВОССТАНОВЛЕНИЕ-ТРЕКА.txt)"
            )
        else:
            print("  APIPass не отдал готовые треки — восстановить нельзя.")
        sys.exit(1)

    task_id = row["task_id"]
    print("=== SongForge DB ===")
    print(f"  production_id: {row['id']}")
    print(f"  title:         {row['title']}")
    print(f"  status:        {row['status']}")
    print(f"  created_at:    {row['created_at']}")
    print(f"  task_id:       {task_id}")
    print(f"  fail_msg:      {row['fail_msg'] or '—'}")
    print(f"  music_url_a:   {'есть' if row['music_url_a'] else 'нет'}")
    print(f"  music_url_b:   {'есть' if row['music_url_b'] else 'нет'}")
    provider = row["music_provider"] if "music_provider" in row.keys() else "apipass"
    print(f"  music_provider:{provider}")

    print(f"\n=== Music API ({provider}) recordInfo ===")
    try:
        status = MusicProviderService().get_status(task_id, provider=provider)
    except Exception as exc:
        print(f"  ОШИБКА запроса music API: {exc}")
        sys.exit(1)

    print(f"  state:         {status['state']}")
    print(f"  fail_msg:      {status.get('fail_msg') or '—'}")
    print(f"  tracks parsed: {len(status.get('tracks') or [])}")

    for i, track in enumerate(status.get("tracks") or []):
        url = track.audio_url if hasattr(track, "audio_url") else track.get("audio_url", "")
        print(f"  track[{i}] url: {'есть' if url else 'НЕТ'}")

    print("\n=== Диагноз ===")
    ap_state = (status["state"] or "").lower()
    db_status = row["status"]

    if ap_state == "success" and len(status.get("tracks") or []) > 0:
        if db_status == "success" and row["music_url_a"]:
            print("  Всё согласовано. Песня в БД — смотрите «История» на сайте.")
        elif db_status == "generating":
            print(
                "  APIPass УЖЕ готов, но сайт не дождался (таймаут опроса ~4 мин).\n"
                "  Песня НЕ попала в «Историю» — нужно догрузить вручную (скрипт восстановления)."
            )
        elif db_status == "success" and not row["music_url_a"]:
            print("  APIPass отдал треки, но URL не сохранились в БД — баг парсинга.")
        else:
            print(f"  APIPass success, БД status={db_status} — рассинхрон.")
    elif ap_state == "success" and not status.get("tracks"):
        print(
            "  APIPass пишет success, но треки не распарсились (формат ответа).\n"
            "  Сайт крутил опрос до таймаута — типичная причина «попробуйте ещё раз»."
        )
    elif ap_state in {"fail", "failed"}:
        print("  APIPass сообщил об ошибке — списание могло быть, трек не создан.")
    else:
        print(f"  APIPass ещё в работе или неизвестный state: {ap_state}")

    if db_status == "generating" and ap_state not in {"success", "fail", "failed"}:
        print("  Генерация ещё идёт — подождите и обновите проверку.")

    if do_fix and ap_state == "success" and status.get("tracks"):
        if db_status == "success" and row["music_url_a"]:
            print("\n=== --fix ===")
            print("  Уже восстановлено, fix не нужен.")
        else:
            HistoryService().update_task_result(
                task_id=task_id,
                status="success",
                tracks=status["tracks"],
            )
            print("\n=== --fix ===")
            print("  Записали треки в БД. Обновите сайт → Профиль → История.")
    elif do_fix:
        print("\n=== --fix ===")
        print("  Восстановление невозможно: APIPass не отдал готовые треки.")


if __name__ == "__main__":
    main()