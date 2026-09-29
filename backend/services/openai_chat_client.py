"""Обычный чат OpenAI-формата: модель в теле письма, один адрес на все модели.

Так ходят Grok (api.x.ai), прямой Gemini и Cloudflare. Kie сюда не входит:
у него имя модели стоит в адресе.
"""

from __future__ import annotations

from typing import Any

import requests

from backend.logger import log


class OpenaiChatClient:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key.strip()
        self._extra = extra_headers or {}

    def complete(
        self,
        system_prompt: str,
        user_text: str,
        *,
        model: str,
        max_tokens: int = 400,
        temperature: float = 0.7,
        timeout: int = 45,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra,
        }
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        response = requests.post(self._url, headers=headers, json=body, timeout=timeout)
        if response.status_code >= 400:
            raise RuntimeError(
                f"{self.name} {model} error {response.status_code}: {response.text[:400]}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(f"{self.name} {model} non-json response") from exc
        if isinstance(data, dict) and data.get("code") not in (None, 200):
            raise RuntimeError(f"{self.name} {model} response: {data!r}"[:500])
        text = _extract_text(data if isinstance(data, dict) else {})
        if not text:
            raise RuntimeError(f"{self.name} {model} empty response: {data!r}"[:500])
        log.info("%s/%s response received (%s chars)", self.name, model, len(text))
        return text


def _extract_text(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    return ""
