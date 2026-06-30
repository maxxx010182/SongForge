from backend.services.yandex_client import YandexClient
from backend.utils.text import clean_text


class ConsultantService:
    SYSTEM = (
        "Ты AI-консультант сервиса «СоздайСвоюПесню» (SongForge). "
        "Помогаешь пользователю создать коммерческую песню без знания промптов. "
        "Отвечай кратко, дружелюбно, на русском. "
        "Объясняй простым языком. "
        "Цены: 1 генерация = 199₽ (2 варианта), пакеты 3/5/10. "
        "2 бесплатные генерации при старте. "
        "Генерация текста бесплатна. Музыка занимает 1–3 минуты. "
        "Подсказывай, как улучшить идею для более сильного трека."
    )

    FAQ = {
        "цена": "1 генерация = 199₽, это 2 варианта песни. Пакеты: 3 за 499₽, 5 за 799₽, 10 за 1199₽.",
        "сколько": "Текст — 10–20 секунд. Музыка — обычно 1–3 минуты.",
        "жанр": "Просто опишите идею — AI-продюсер сам подберёт жанр, темп, вокал и стиль.",
        "бесплатн": "При первом визите — 2 бесплатные генерации. Текст песни всегда бесплатный.",
        "оплат": "Оплата скоро через Продамус (карты и СБП). Сейчас можно тестировать генерацию.",
    }

    def __init__(self) -> None:
        self._yandex = YandexClient()

    def reply(self, message: str, context: str = "") -> str:
        message = message.strip()
        if not message:
            return "Напишите, чем помочь — идея песни, жанр, цены или как работает сервис."

        user_text = message
        if context.strip():
            user_text = f"Контекст: {context.strip()}\n\nВопрос: {message}"

        try:
            answer = self._yandex.complete(
                self.SYSTEM,
                user_text,
                max_tokens=350,
                temperature=0.6,
            )
            return clean_text(answer)
        except Exception:
            low = message.lower()
            for key, value in self.FAQ.items():
                if key in low:
                    return value
            return (
                "Опишите идею песни своими словами — AI-продюсер сам подберёт стиль. "
                "Если нужна помощь с ценами или процессом — спрашивайте!"
            )