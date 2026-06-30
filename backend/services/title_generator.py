from backend.models import ProductionPlan
from backend.services.yandex_client import YandexClient
from backend.utils.text import clean_text, truncate


class TitleGenerator:
    def __init__(self, yandex: YandexClient) -> None:
        self._yandex = yandex

    def generate(self, idea: str, plan: ProductionPlan) -> str:
        system_prompt = (
            "Придумай короткое запоминающееся название песни на русском языке. "
            "Без кавычек, без пояснений, максимум 4 слова."
        )
        user_text = (
            f"Идея: {idea}\n"
            f"Жанр: {plan.genre} / {plan.subgenre}\n"
            f"Настроение: {plan.mood}"
        )
        try:
            title = self._yandex.complete(system_prompt, user_text, max_tokens=40, temperature=0.8)
            title = clean_text(title).strip("\"'«»")
            if title:
                return truncate(title, 75)
        except Exception:
            pass

        words = [w for w in idea.split() if w.strip()]
        fallback = " ".join(words[:4]) if words else "Моя песня"
        return truncate(fallback, 75)