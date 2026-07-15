"""OpenAI-compatible LLM (VseGPT, DeepSeek proxy и т.п.).

Один API-ключ, разные model id под задачи:
  - MODEL_PRO  → сильная модель (тексты песен)
  - MODEL_LITE → быстрая/дешёвая (план, бот, style)
"""

from __future__ import annotations

import requests

from backend.logger import log
from backend.settings import (
    LLM_MODEL_LITE,
    LLM_MODEL_PRO,
    OPENAI_COMPAT_API_KEY,
    OPENAI_COMPAT_BASE,
)


class OpenaiCompatClient:
    """Совместим по интерфейсу с YandexClient (MODEL_* + complete)."""

    # Логические имена — как у Yandex, чтобы не трогать lyrics_craft цепочки
    MODEL_LITE = "yandexgpt-lite"
    MODEL_PRO = "yandexgpt"

    def __init__(self) -> None:
        base = (OPENAI_COMPAT_BASE or "https://api.vsegpt.ru/v1").rstrip("/")
        self._url = f"{base}/chat/completions"

    def _resolve_model(self, model: str) -> str:
        key = (model or "").strip()
        if key in {self.MODEL_PRO, "yandexgpt", "pro", "lyrics"}:
            return LLM_MODEL_PRO
        if key in {self.MODEL_LITE, "yandexgpt-lite", "lite", "consultant", "fast"}:
            return LLM_MODEL_LITE
        # Уже полный id провайдера: deepseek/deepseek-v4-flash
        if "/" in key or key.startswith("openai/") or key.startswith("google/"):
            return key
        return LLM_MODEL_LITE

    def complete(
        self,
        system_prompt: str,
        user_text: str,
        *,
        max_tokens: int = 400,
        temperature: float = 0.7,
        model: str = MODEL_LITE,
    ) -> str:
        if not OPENAI_COMPAT_API_KEY:
            raise RuntimeError("OPENAI_COMPAT_API_KEY is not configured")

        model_id = self._resolve_model(model)
        headers = {
            "Authorization": f"Bearer {OPENAI_COMPAT_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = requests.post(self._url, headers=headers, json=body, timeout=90)
        response.raise_for_status()
        data = response.json()
        try:
            text = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected LLM response: {data!r}") from exc
        log.info(
            "OpenAI-compat/%s response received (%s chars)",
            model_id,
            len(text),
        )
        return text
