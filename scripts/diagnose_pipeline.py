"""Пошаговая диагностика цепочки AI-продюсер → APIPass."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.database.db import get_connection, init_db
from backend.settings import APIPASS_API_KEY, YANDEX_API_KEY, YANDEX_FOLDER_ID


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL {msg}")


def warn(msg: str) -> None:
    print(f"  WARN {msg}")


def step_env() -> bool:
    print("\n[1] Переменные окружения")
    good = True
    if YANDEX_API_KEY:
        ok("YANDEX_API_KEY задан")
    else:
        fail("YANDEX_API_KEY пуст — AI-продюсер не сможет работать")
        good = False
    if YANDEX_FOLDER_ID:
        ok(f"YANDEX_FOLDER_ID = {YANDEX_FOLDER_ID}")
    else:
        fail("YANDEX_FOLDER_ID пуст")
        good = False
    if APIPASS_API_KEY:
        ok("APIPASS_API_KEY задан")
    else:
        fail("APIPASS_API_KEY пуст — Suno не запустится")
        good = False
    return good


def step_yandex() -> bool:
    print("\n[2] YandexGPT (быстрый ping)")
    try:
        from backend.services.yandex_client import YandexClient

        t0 = time.perf_counter()
        text = YandexClient().complete(
            "Ответь одним словом: ping",
            "ping",
            max_tokens=8,
            temperature=0.1,
        )
        dt = time.perf_counter() - t0
        ok(f"ответ за {dt:.1f} сек: {text[:40]!r}")
        if dt > 20:
            warn("YandexGPT отвечает медленно — на мобиле create-song может «висеть» минуты")
        return True
    except Exception as exc:
        fail(str(exc))
        return False


def step_db() -> None:
    print("\n[3] База generations (последние записи)")
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, task_id, status, created_at, fail_msg
            FROM generations
            ORDER BY created_at DESC
            LIMIT 8
            """
        ).fetchall()

    if not rows:
        warn("записей нет — create-song ещё не доходил до сохранения")
        return

    for row in rows:
        rid = (row["id"] or "")[:8]
        task = row["task_id"] or "—"
        print(
            f"  • {row['created_at']} | {row['status']:10} | task={task} | "
            f"{row['title'][:40]!r} | id={rid}..."
        )
        if row["status"] == "planned" and not row["task_id"]:
            warn(
                "status=planned без task_id → Yandex отработал, "
                "но APIPass createTask НЕ вызван или упал"
            )
        elif row["status"] == "generating" and row["task_id"]:
            ok(f"task_id есть — проверьте этот ID в личном кабинете APIPass: {task}")
        elif row["status"] == "failed":
            warn(f"ошибка: {row['fail_msg']}")


def step_apipass_dry() -> bool:
    print("\n[4] APIPass createTask (тест НЕ запускаем — только проверка клиента)")
    try:
        from backend.services.apipass_client import ApiPassClient

        ApiPassClient()._ensure_key()
        ok("клиент инициализируется, ключ есть")
        warn(
            "реальный createTask не вызываем (списание кредитов). "
            "Если в БД нет task_id — сбой между шагами 2 и APIPass."
        )
        return True
    except Exception as exc:
        fail(str(exc))
        return False


def main() -> None:
    print("SongForge — диагностика цепочки генерации")
    print("=" * 50)
    env_ok = step_env()
    yandex_ok = step_yandex() if env_ok else False
    step_db()
    apipass_ok = step_apipass_dry() if env_ok else False

    print("\n[Итог]")
    print(
        "Цепочка: UI → POST /api/create-song → YandexGPT (3–5 вызовов) "
        "→ APIPass createTask → polling /api/music/status"
    )
    print("84% на экране — НЕ реальный прогресс Suno. Это таймер UI до 88%.")
    if not yandex_ok:
        print("Вероятная поломка: этап YandexGPT внутри /api/create-song.")
    elif env_ok and apipass_ok:
        print(
            "Если в APIPass пусто, смотрите БД: planned без task_id = до Suno не дошли; "
            "generating с task_id = задача создана, ищите task_id в APIPass."
        )


if __name__ == "__main__":
    main()