"""AI-помощник на сайте. Только пользовательские знания — без .env/SSH/админки."""

from __future__ import annotations

from pathlib import Path

from backend.services.llm_factory import get_llm_client
from backend.settings import ROOT_DIR
from backend.utils.text import clean_text

_SUPPORT_EMAIL = "support@sozdaipesnu.ru"
_USER_GUIDE = ROOT_DIR / "docs" / "public" / "USER_GUIDE.md"


def _load_user_guide_excerpt(max_chars: int = 6000) -> str:
    try:
        text = _USER_GUIDE.read_text(encoding="utf-8")
        if len(text) > max_chars:
            return text[:max_chars] + "\n…(сокращено)"
        return text
    except OSError:
        return ""


class ConsultantService:
    SYSTEM_BASE = (
        "Ты AI-помощник сервиса «СоздайСвоюПесню» (сайт sozdaipesnu.ru). "
        "Помогаешь обычным людям: создать песню, понять ноты, оплату, вход. "
        "Отвечай кратко, дружелюбно, по-русски, простым языком. "
        "Не используй слова: API, сервер, webhook, SSH, .env, pm2, task_id. "
        "Не выдумывай функции, которых нет. "
        "Не проси личные пароли и коды из писем. "
        "\n\n"
        "Факты о сервисе:\n"
        "• После входа — 1 пробная генерация (2 варианта, превью ~30 сек).\n"
        "• 1 нота = 1 создание песни = 2 полных трека в фонотеку.\n"
        "• Пакеты: 1 нота 299 ₽, 3 — 749 ₽, 5 — 1199 ₽, 10 — 1799 ₽.\n"
        "• Оплата через GetPlatinum (карты, СБП и др.).\n"
        "• Промокод (если выдан) вводится на форме оплаты GetPlatinum, не на главной сайта.\n"
        "• Музыка обычно 3–5 минут. AI-продюсер — быстро; Расширенный — свой текст и настройки.\n"
        "• Жанр лучше писать в идее словами (реп, рок, джаз…).\n"
        f"• Официальная поддержка: только {_SUPPORT_EMAIL} "
        "(не личные соцсети владельца).\n"
        "• Часы: email — ответ обычно в течение 24 ч; живые каналы — ежедневно 8:00–20:00 МСК, "
        "в выходные/праздники возможна задержка.\n"
        "\n"
        "Если вопрос про сбой оплаты, пропавшие ноты, возврат денег, удаление аккаунта — "
        f"вежливо направь написать на {_SUPPORT_EMAIL} и кратко что указать "
        "(email на сайте, время, что делали).\n"
        "Если про идею песни / как пользоваться — помоги сам по гайду ниже.\n"
    )

    FAQ = {
        "цена": (
            "1 нота = 299 ₽ — одна генерация и 2 варианта песни. "
            "Пакеты: 3 ноты — 749 ₽, 5 — 1199 ₽, 10 — 1799 ₽. Раздел «Пакеты»."
        ),
        "сколько": "Текст — обычно быстро. Музыка — примерно 3–5 минут, иногда дольше.",
        "жанр": (
            "Напишите жанр в описании идеи (реп, рок, джаз…). "
            "В Расширенном режиме можно выбрать списком или своими словами."
        ),
        "бесплатн": (
            "После входа — 1 пробная генерация на аккаунт. "
            "Дальше нужны ноты. Без входа создать песню нельзя."
        ),
        "пробн": (
            "1 пробная на аккаунт: 2 варианта. "
            "Полные версии — после покупки нот (смотрите подсказки на сайте)."
        ),
        "нот": (
            "1 нота списывается при создании песни — 2 полных варианта в фонотеку. "
            "Пополнить: раздел «Пакеты»."
        ),
        "оплат": (
            "Пакеты → «Перейти к оплате» → форма GetPlatinum. "
            f"Если деньги списались, а нот нет — напишите на {_SUPPORT_EMAIL}."
        ),
        "промо": (
            "Промокод (если вам выдали) вводят на странице оплаты GetPlatinum, "
            "не в студии. Не сработало — поддержка: " + _SUPPORT_EMAIL
        ),
        "вход": (
            "Войдите по email (код на почту) или через Telegram/VK, если кнопки видны. "
            "Код не пришёл — проверьте «Спам», запросите снова."
        ),
        "поддерж": (
            f"Пишите на {_SUPPORT_EMAIL}. Укажите email на сайте и суть проблемы. "
            "Ответ обычно в течение 24 часов."
        ),
        "support": (
            f"Официальный email: {_SUPPORT_EMAIL}."
        ),
    }

    def __init__(self) -> None:
        self._llm = get_llm_client()
        self._guide = _load_user_guide_excerpt()

    def _system_prompt(self) -> str:
        base = self.SYSTEM_BASE
        if self._guide:
            base += "\n\nКраткая инструкция для пользователей (опирайся на неё):\n" + self._guide
        return base

    def reply(self, message: str, context: str = "") -> str:
        message = message.strip()
        if not message:
            return (
                "Напишите, чем помочь — идея песни, ноты, оплата или вход. "
                f"Сложный сбой — { _SUPPORT_EMAIL }."
            )

        user_text = message
        if context.strip():
            user_text = f"Контекст: {context.strip()}\n\nВопрос: {message}"

        try:
            # LITE — дешёвая/быстрая модель для живого общения
            answer = self._llm.complete(
                self._system_prompt(),
                user_text,
                max_tokens=400,
                temperature=0.55,
                model=self._llm.MODEL_LITE,
            )
            return clean_text(answer)
        except Exception:
            low = message.lower()
            for key, value in self.FAQ.items():
                if key in low:
                    return value
            return (
                "Опишите идею песни своими словами или спросите про ноты и оплату. "
                f"Если что-то сломалось — { _SUPPORT_EMAIL }."
            )
