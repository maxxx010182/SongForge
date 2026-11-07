"""Тексты писем бота. Напоминания общие: без цены, без имени и без цитат анкеты."""

from __future__ import annotations

from backend.database.db import get_connection
from backend.settings import GUEST_GENERATION_LIMIT


def trial_is_open(user_id: str | None) -> bool:
    """Проба ещё есть. Без аккаунта считаем, что первая песня впереди."""
    uid = (user_id or "").strip()
    if not uid:
        return True
    with get_connection() as conn:
        row = conn.execute(
            "SELECT trial_generations_used FROM users WHERE id = ?",
            (uid,),
        ).fetchone()
    used = int(row["trial_generations_used"]) if row else 0
    return used < GUEST_GENERATION_LIMIT


def price_reply(*, trial_open: bool) -> str:
    """Цифр нет. Ответ один и до пробы, и после."""
    del trial_open
    return (
        "Первые демо можно послушать бесплатно прямо сейчас. "
        "Послушать и скачать полные версии можно по ценам, которые сейчас указаны "
        "на сайте, в разделе пакеты."
    )


def studio_letter(_contact: dict, step: int) -> str:
    """Песню ещё не запускали. step 0..3 = час, ближайший вечер, день 3, день 7."""
    n = step if step < 3 else 3
    if n == 0:
        return (
            "Студия уже ждёт. Песня начнётся, когда нажмёшь «Создать песню»."
        )
    if n == 1:
        return (
            "Там всё на месте. Одно нажатие, и через несколько минут будут два варианта."
        )
    if n == 2:
        return "Два варианта можно просто послушать. Платить заранее не нужно."
    return "Последний раз напомню: песня так и не запускалась. Ссылка та же."


def survey_letter(_contact: dict, step: int) -> str:
    """Бросил анкету. Три разных письма, потом тишина."""
    n = step if step < 2 else 2
    if n == 0:
        return (
            "Песня ещё не собрана. Можно вернуться и закончить. Это пара вопросов."
        )
    if n == 1:
        return "Можно просто нажимать готовые ответы. Свою деталь можно пропустить."
    return "Дальше напоминать не буду. Вернуться можно с того же места."


def ready_letter(_contact: dict) -> str:
    """Через ~5 минут, если демо ещё не слушали."""
    return "Два варианта уже готовы. Послушай и выбери, какой ближе."


def keep_letter(_contact: dict, kind: str, *, listened: bool = False) -> str:
    """Письмо, если песня есть, а покупки нет.

    kind: d1, d4, d7, d11, d14. Старые имена очереди тоже понимаем.
    Цифр и цитат анкеты нет. Слушал человек или нет, текст дня один.
    """
    del listened
    key = {
        "keep_d1": "d1",
        "keep_d3": "d1",
        "unpaid_preview": "d1",
        "d1": "d1",
        "keep_d4": "d4",
        "d4": "d4",
        "keep_d7": "d7",
        "unpaid_expert": "d7",
        "d7": "d7",
        "keep_d10": "d11",
        "keep_d11": "d11",
        "unpaid_tip": "d11",
        "d11": "d11",
        "keep_d14": "d14",
        "unpaid_weekly": "d14",
        "d14": "d14",
    }.get(kind, "d14")
    if key == "d1":
        return "Демо ещё на месте. Послушать можно в фонотеке."
    if key == "d4":
        return "Оба варианта всё ещё можно послушать."
    if key == "d7":
        return "Если ещё не выбрал, оба лежат в фонотеке."
    if key == "d11":
        return "Это демо хранится ещё три дня."
    return "Сегодня последний день, когда это демо ещё можно забрать."
