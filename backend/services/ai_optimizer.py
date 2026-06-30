from backend.services.yandex_client import YandexClient
from backend.utils.text import clean_text


class AiOptimizer:
    def __init__(self, yandex: YandexClient) -> None:
        self._yandex = yandex

    def optimize(self, idea: str) -> str:
        idea = idea.strip()
        if len(idea) < 12:
            return idea

        system_prompt = (
            "Ты музыкальный продюсер. Улучши идею песни пользователя: "
            "сделай её конкретнее, эмоциональнее и пригодной для генерации хита. "
            "Сохрани смысл и язык пользователя. "
            "Ответ — одно предложение или два коротких, без пояснений."
        )
        try:
            optimized = self._yandex.complete(system_prompt, idea, max_tokens=120, temperature=0.5)
            return clean_text(optimized) or idea
        except Exception:
            return idea