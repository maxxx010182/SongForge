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
    """Через ~5 минут, если демо ещё не слушали."""
    named = _named(contact)
    if named:
        return (
            f"Песня {named} готова 🎶 Два варианта: текст один, музыка разная. "
            "Послушай демо-отрывки и выбери, какой ближе."
        )
    return (
        "Песня готова 🎶 Два варианта: текст один, музыка разная. "
        "Послушай демо-отрывки и выбери, какой ближе."
    )


def keep_letter(contact: dict, kind: str, *, listened: bool = False) -> str:
    """Письмо, если песня есть, а покупки нет.

    kind: d1, d4, d7, d11, d14. Старые имена очереди тоже понимаем.
    Пакеты нот и МузПлощадку как угрозу сюда не ставим.
    """
    named = _named(contact)
    one, _, _, _ = _note_prices()
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
        if listened:
            return (
                "Какой вариант понравился больше? "
                f"Забрать обе полные версии — 1 нота, {one} ₽."
            )
        if named:
            return (
                f"Два демо-варианта песни {named} ждут в фонотеке. "
                "Отрывки по 90 секунд — бесплатно. Нажми «Послушать»."
            )
        return (
            "Два демо-варианта ждут в фонотеке. "
            "Отрывки по 90 секунд — бесплатно. Нажми «Послушать»."
        )
    if key == "d4":
        song = f"песни {named}" if named else "песни"
        return (
            f"Что даёт 1 нота ({one} ₽):\n"
            f"• обе полные версии {song}, а не отрывки\n"
            "• скачивание — можно отправить или включить где угодно\n"
            "• публикация на МузПлощадке\n"
            "• текст песни"
        )
    if key == "d7":
        return (
            "Если варианты не попали — песню можно пересоздать: новая генерация тоже "
            f"стоит 1 ноту ({one} ₽) и даёт ещё два варианта. Для более точного результата "
            "есть расширенный режим — там больше настроек под то звучание, которое ты ищешь."
        )
    if key == "d11":
        head = f"Демо песни {named} хранится ещё 3 дня." if named else "Демо хранится ещё 3 дня."
        return (
            f"{head} Потом выкупить его не получится.\n"
            "\n"
            "Если варианты не подошли, их можно пересоздать — обычным способом или "
            "в расширенном режиме с более точной настройкой.\n"
            "\n"
            f"Забрать полные версии — 1 нота, {one} ₽."
        )
    if named:
        return (
            f"Сегодня последний день, когда песню {named} ещё можно забрать. "
            f"Потом это демо уже не купить. 1 нота — {one} ₽ — и обе полные версии твои."
        )
    return (
        "Сегодня последний день, когда эту песню ещё можно забрать. "
        "Потом это демо уже не купить. 1 нота — "
        f"{one} ₽ — и обе полные версии твои."
    )
