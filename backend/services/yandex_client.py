import requests

from backend.logger import log
from backend.settings import YANDEX_API_KEY, YANDEX_FOLDER_ID


class YandexClient:
    MODEL_LITE = "yandexgpt-lite"
    MODEL_PRO = "yandexgpt"

    def __init__(self) -> None:
        self._url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    def complete(
        self,
        system_prompt: str,
        user_text: str,
        *,
        max_tokens: int = 400,
        temperature: float = 0.7,
        model: str = MODEL_LITE,
    ) -> str:
        if not YANDEX_API_KEY:
            raise RuntimeError("YANDEX_API_KEY is not configured")

        model_key = self.MODEL_PRO if model == self.MODEL_PRO else self.MODEL_LITE
        headers = {
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "modelUri": f"gpt://{YANDEX_FOLDER_ID}/{model_key}/latest",
            "completionOptions": {
                "temperature": temperature,
                "maxTokens": max_tokens,
            },
            "messages": [
                {"role": "system", "text": system_prompt},
                {"role": "user", "text": user_text},
            ],
        }

        response = requests.post(self._url, headers=headers, json=body, timeout=45)
        response.raise_for_status()
        text = response.json()["result"]["alternatives"][0]["message"]["text"].strip()
        log.info("YandexGPT/%s response received (%s chars)", model_key, len(text))
        return text