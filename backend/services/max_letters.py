"""Тексты писем бота. Кнопка даёт готовую форму. Своё имя в письмо не вставляем."""

from __future__ import annotations

from backend.database.db import get_connection
from backend.services.max_funnel import is_just_plot, is_skip, whom_for_phrase
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


def _note_prices() -> tuple[int, int, int, int]:
    from backend.services.payment_service import PACKAGES

    return (
        int(PACKAGES["notes_1"]["price_rub"]),
        int(PACKAGES["notes_3"]["price_rub"]),
        int(PACKAGES["notes_5"]["price_rub"]),
        int(PACKAGES["notes_10"]["price_rub"]),
    )


def price_reply(*, trial_open: bool) -> str:
    one, three, five, ten = _note_prices()
    packs = f"Пакетом выгоднее: 3 ноты — {three} ₽, 5 — {five} ₽, 10 — {ten} ₽."
    if trial_open:
        return (
            "Первая проба бесплатна: создаёшь песню и слушаешь два демо-варианта "
            "отрывками по 90 секунд.\n"
            f"Понравилось — забираешь полные версии за 1 ноту ({one} ₽). "
            "За неё обе версии: слушать целиком, скачать, опубликовать на МузПлощадке.\n"
            f"{packs}\n"
            "\n"
            "Продолжим?"
        )
    return (
        f"Одна песня — 1 нота ({one} ₽): сразу две полные версии, скачивание и публикация.\n"
        f"{packs}\n"
        "\n"
        "Продолжим?"
    )


def _role(contact: dict) -> str:
    if (contact.get("segment") or "") == "business":
        return "business"
    whom = (contact.get("brief_whom") or "").strip()
    if is_just_plot(whom, contact.get("segment") or "") or not whom:
        return "plain"
    return "gift"


def _named(contact: dict) -> str:
    """«для мамы» только если адресат — кнопка. Своё имя сюда не подставляем."""
    if _role(contact) != "gift":
        return ""
    return whom_for_phrase(contact.get("brief_whom") or "")


def _detail(contact: dict) -> str:
    raw = " ".join((contact.get("brief_detail") or "").split())
    if not raw or is_skip(raw):
        return ""
    if len(raw) > 80:
        raw = raw[:79].rstrip() + "…"
    return raw


def studio_letter(contact: dict, step: int) -> str:
    """Песню ещё не запускали. step 0..3 = ближайший вечер, следующий, день 3, день 7."""
    named = _named(contact)
    detail = _detail(contact)
    n = step if step < 3 else 3
    trial = trial_is_open(contact.get("user_id"))
    one, _, _, _ = _note_prices()
    if n == 0:
        if named:
            text = (
                f"Анкета {named} уже в студии, но песни пока нет — её нужно запустить. "
                "Нажми «Создать песню»: примерно через 3 минуты будут два варианта."
            )
        else:
            text = (
                "Анкета уже в студии, но песни пока нет — её нужно запустить. "
                "Нажми «Создать песню»: примерно через 3 минуты будут два варианта."
            )
        if trial:
            text += "\n\nПервая проба бесплатна: 2 демо-варианта по 90 секунд."
        return text
    if n == 1:
        if detail:
            text = (
                f"«{detail}» — из этого может получиться строчка в песне. "
                "Нажми «Создать песню» и послушай, как она поётся."
            )
        else:
            text = (
                "Все пожелания к песне уже вписаны в студии. "
                "Одна кнопка — и примерно через 3 минуты два варианта."
            )
        if trial:
            text += "\n\nЭто бесплатно."
        return text
    if n == 2:
        if trial:
            return (
                "Как это работает:\n"
                "1. Нажимаешь «Создать песню».\n"
                "2. Примерно через 3 минуты — два варианта: текст один, музыка разная.\n"
                "3. Слушаешь демо-отрывки по 90 секунд — бесплатно.\n"
                f"4. Понравилось — забираешь обе полные версии за {one} ₽.\n"
                "Платить заранее не нужно."
            )
        return (
            f"Одна генерация — 1 нота ({one} ₽) — и сразу две полные версии: "
            "слушать, скачать, опубликовать. Анкета уже в студии."
        )
    if named:
        return f"Последнее напоминание: анкета {named} ждёт в студии. Кнопка та же."
    return "Последнее напоминание: анкета ждёт в студии. Кнопка та же."


def survey_letter(contact: dict, step: int) -> str:
    """Бросил анкету. Три разных письма, потом тишина."""
    named = _named(contact)
    n = step if step < 2 else 2
    if n == 0:
        if named:
            text = (
                f"Анкета песни {named} остановилась на середине. "
                "Осталась пара вопросов — и можно в студию."
            )
        else:
            text = (
                "Анкета песни остановилась на середине. "
                "Осталась пара вопросов — и можно в студию."
            )
        if trial_is_open(contact.get("user_id")):
            text += "\n\nПервая проба бесплатна: 2 демо-варианта по 90 секунд."
        return text
    if n == 1:
        return (
            "Не знаешь, что ответить? На каждый вопрос можно просто нажать готовый вариант, "
            "а деталь — пропустить. Песня соберётся и так, детали только делают её точнее."
        )
    return (
        "Последнее напоминание про эту анкету. "
        "Ответы сохранены — вернуться можно в любой момент."
    )


def ready_letter(contact: dict) -> str:
    """Через ~5 минут после того, как песня зазвучала."""
    named = _named(contact)
    if named:
        return (
            f"Два варианта {named} уже звучат. "
            "Нажми «Послушать» — откроется песня."
        )
    return (
        "Два варианта уже звучат. "
        "Нажми «Послушать» — откроется песня."
    )


def keep_letter(contact: dict, step: int) -> str:
    """Письмо, если песня есть, а покупки нет. step 0..3 = дни 3, 7, 10, 14."""
    named = _named(contact)
    n = step if step < 3 else 3
    whom = named
    whom_for = named
    if n == 0:
        if whom:
            return (
                f"Песня {whom_for} уже звучит. Осталось выбрать, какую оставить. "
                f"Получились два варианта, оба {whom_for}. "
                "Один теплее, другой живее. Нажми «Послушать» — откроется песня."
            )
        return (
            "Она уже звучит. Осталось выбрать, какую оставить. "
            "На днях получились два варианта. Один теплее, другой живее. "
            "Нажми «Послушать» — откроется песня."
        )
    if n == 1:
        if whom:
            return (
                f"Песню {whom_for} уже можно поставить. "
                "Минута в наушниках — и слышно, та ли это. "
                "Нажми «Послушать» — откроется песня."
            )
        return (
            "Два варианта всё ещё ждут. Её уже можно включить вечером. "
            "Нажми «Послушать» — откроется песня."
        )
    if n == 2:
        if whom:
            return (
                "Если первые варианты прошли мимо — в студии можно собрать звучание иначе. "
                f"Песня {whom_for} уже ждёт. Нажми «Послушать»."
            )
        return (
            "Если первые варианты прошли мимо — в студии можно собрать звучание иначе. "
            "Песня уже ждёт. Нажми «Послушать»."
        )
    if whom:
        return (
            f"Сегодня последний день, когда песню {whom_for} ещё можно забрать. "
            "Потом это демо уже не купить. Нажми «Послушать»."
        )
    return (
        "Сегодня последний день, когда эту песню ещё можно забрать. "
        "Потом это демо уже не купить. Нажми «Послушать»."
    )
