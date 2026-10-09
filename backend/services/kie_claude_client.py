"""Claude на Kie: другой адрес, не chat/completions.

Куплет Сонета 5.5 прошёл так: POST /anthropic/v1/messages,
без поля temperature. С temperature Kie может ответить 400,
и модель на время закроется.
"""

from __future__ import annotations

from typing import Any

import requests

from backend.logger import log
from backend.settings import KIE_API_KEY, KIE_BASE


class KieClaudeClient:
    def __init__(self) -> None:
        self._base = (KIE_BASE or "https://api.kie.ai").rstrip("/")

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
        del temperature  # в это письмо не кладём: проверенный куплет шёл без него
        if not KIE_API_KEY:
            raise RuntimeError("KIE_API_KEY is not configured")
        url = f"{self._base}/anthropic/v1/messages"
        headers = {
            "Authorization": f"Bearer {KIE_API_KEY}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": user_text}],
            "max_tokens": max_tokens,
            "stream": False,
        }
        if system_prompt:
            body["system"] = system_prompt
        response = requests.post(url, headers=headers, json=body, timeout=timeout)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Kie {model} error {response.status_code}: {response.text[:400]}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Kie {model} non-json response") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected Kie response: {data!r}"[:500])
        if data.get("code") not in (None, 200):
            raise RuntimeError(f"Unexpected Kie response: {data!r}"[:500])
        error = data.get("error")
        if isinstance(error, dict) and not _extract_text(data):
            message = error.get("message") or error
            raise RuntimeError(f"Kie {model} error: {message}")
        text = _extract_text(data)
        if not text and isinstance(data.get("data"), dict):
            text = _extract_text(data["data"])
        if not text:
            raise RuntimeError(f"Unexpected Kie response: {data!r}"[:500])
        log.info("Kie/%s response received (%s chars)", model, len(text))
        return text


def _extract_text(data: dict[str, Any]) -> str:
    content = data.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
            continue
        if not isinstance(part, dict):
            continue
        if part.get("type") not in (None, "text"):
            continue
        if isinstance(part.get("text"), str):
            parts.append(part["text"])
    return "\n".join(piece.strip() for piece in parts if piece and piece.strip()).strip()
