"""Фабрика LLM: yandex | openai_compat (VseGPT и др.).

Один ключ провайдера → разные модели через LLM_MODEL_PRO / LLM_MODEL_LITE.
"""

from __future__ import annotations

from typing import Protocol

from backend.logger import log
from backend.settings import LLM_PROVIDER


class LlmClient(Protocol):
    MODEL_LITE: str
    MODEL_PRO: str

    def complete(
        self,
        system_prompt: str,
        user_text: str,
        *,
        max_tokens: int = 400,
        temperature: float = 0.7,
        model: str = ...,
    ) -> str: ...


_client: LlmClient | None = None


def get_llm_client() -> LlmClient:
    global _client
    if _client is not None:
        return _client

    provider = (LLM_PROVIDER or "yandex").strip().lower()
    if provider in {"openai_compat", "vsegpt", "openai", "deepseek_proxy"}:
        from backend.services.openai_compat_client import OpenaiCompatClient

        _client = OpenaiCompatClient()
        log.info("LLM provider: openai_compat (VseGPT/OpenAI-compatible)")
    else:
        from backend.services.yandex_client import YandexClient

        _client = YandexClient()
        log.info("LLM provider: yandex")
    return _client
