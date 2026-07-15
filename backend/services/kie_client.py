"""Клиент Kie.ai для текстовых LLM (chat).

У Kie у каждой модели свой path (не один /v1 на всех):
  POST https://api.kie.ai/{model-slug}/v1/chat/completions

По умолчанию:
  LITE → gemini-2.5-flash  (бот, план, быстрые задачи)
  PRO  → gemini-2.5-pro    (тексты песен)

Баланс кредитов: GET /api/v1/chat/credit
"""

from __future__ import annotations

import re
from typing import Any

import requests

from backend.logger import log
from backend.settings import KIE_API_KEY, KIE_BASE, LLM_MODEL_LITE, LLM_MODEL_PRO

# slug модели → path prefix (без ведущего /)
# Можно переопределить через LLM_MODEL_* (просто slug: gemini-2.5-flash)
_DEFAULT_SLUGS = {
    "lite": "gemini-2.5-flash",
    "pro": "gemini-2.5-pro",
}


def _slugify(model_id: str) -> str:
    """Нормализует id к slug path: gemini-2.5-flash."""
    s = (model_id or "").strip().lower()
    if not s:
        return _DEFAULT_SLUGS["lite"]
    # google/gemini-2.5-flash → gemini-2.5-flash
    if "/" in s:
        s = s.split("/")[-1]
    s = s.replace("_", "-")
    # убрать суффикс openai если есть в id
    s = re.sub(r"-openai$", "", s)
    return s


class KieClient:
    """Совместим по интерфейсу с YandexClient / OpenaiCompatClient."""

    MODEL_LITE = "yandexgpt-lite"
    MODEL_PRO = "yandexgpt"

    def __init__(self) -> None:
        self._base = (KIE_BASE or "https://api.kie.ai").rstrip("/")

    def _resolve_slug(self, model: str) -> str:
        key = (model or "").strip()
        if key in {self.MODEL_PRO, "yandexgpt", "pro", "lyrics"}:
            slug = _slugify(LLM_MODEL_PRO or _DEFAULT_SLUGS["pro"])
            return slug if self._is_kie_gemini(slug) else _DEFAULT_SLUGS["pro"]
        if key in {self.MODEL_LITE, "yandexgpt-lite", "lite", "consultant", "fast"}:
            slug = _slugify(LLM_MODEL_LITE or _DEFAULT_SLUGS["lite"])
            return slug if self._is_kie_gemini(slug) else _DEFAULT_SLUGS["lite"]
        # Уже slug / полный id провайдера
        slug = _slugify(key)
        if self._is_kie_gemini(slug):
            return slug
        # неизвестный id → LITE
        return _DEFAULT_SLUGS["lite"]

    @staticmethod
    def _is_kie_gemini(slug: str) -> bool:
        s = (slug or "").lower()
        return s.startswith("gemini")

    def _chat_url(self, slug: str) -> str:
        return f"{self._base}/{slug}/v1/chat/completions"

    def complete(
        self,
        system_prompt: str,
        user_text: str,
        *,
        max_tokens: int = 400,
        temperature: float = 0.7,
        model: str = MODEL_LITE,
    ) -> str:
        if not KIE_API_KEY:
            raise RuntimeError("KIE_API_KEY is not configured")

        slug = self._resolve_slug(model)
        url = self._chat_url(slug)
        headers = {
            "Authorization": f"Bearer {KIE_API_KEY}",
            "Content-Type": "application/json",
        }
        # OpenAI-compatible body. stream=false обязателен (у Kie default=true).
        # include_thoughts=false — не тратить токены на «мысли».
        body: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "stream": False,
            "include_thoughts": False,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        # Pro-модели Kie Gemini: низкий reasoning → быстрее и дешевле
        if "pro" in slug:
            body["reasoning_effort"] = "low"

        response = requests.post(url, headers=headers, json=body, timeout=120)
        if response.status_code >= 400:
            # Если string content не принят — retry с multimodal text blocks
            try:
                err = response.json()
            except Exception:
                err = response.text[:300]
            log.warning(
                "Kie %s HTTP %s: %s — retry array content",
                slug,
                response.status_code,
                err,
            )
            body["messages"] = [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_text}],
                },
            ]
            response = requests.post(url, headers=headers, json=body, timeout=120)

        if response.status_code >= 400:
            raise RuntimeError(
                f"Kie {slug} error {response.status_code}: {response.text[:400]}"
            )

        data = response.json()
        text = self._extract_text(data)
        if not text:
            raise RuntimeError(f"Unexpected Kie response: {data!r}")
        log.info("Kie/%s response received (%s chars)", slug, len(text))
        return text

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        # OpenAI chat.completion
        try:
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts: list[str] = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text" and block.get("text"):
                            parts.append(str(block["text"]))
                        elif "text" in block:
                            parts.append(str(block["text"]))
                    elif isinstance(block, str):
                        parts.append(block)
                return "\n".join(parts).strip()
        except (KeyError, IndexError, TypeError):
            pass
        # Claude-like fallback
        try:
            blocks = data.get("content") or []
            parts = []
            for b in blocks:
                if isinstance(b, dict) and b.get("type") == "text":
                    parts.append(str(b.get("text") or ""))
                elif isinstance(b, dict) and b.get("text"):
                    parts.append(str(b["text"]))
            if parts:
                return "\n".join(parts).strip()
        except (TypeError, AttributeError):
            pass
        return ""

    def get_credits(self) -> float | None:
        """Остаток кредитов Kie (GET /api/v1/chat/credit)."""
        if not KIE_API_KEY:
            return None
        try:
            response = requests.get(
                f"{self._base}/api/v1/chat/credit",
                headers={"Authorization": f"Bearer {KIE_API_KEY}"},
                timeout=15,
            )
            response.raise_for_status()
            body = response.json()
            if body.get("code") in (None, 200):
                return float(body.get("data") or 0)
        except (requests.RequestException, TypeError, ValueError) as exc:
            log.warning("Kie credits check failed: %s", exc)
        return None
