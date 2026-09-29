"""Очередь текстовых моделей.

Сначала Kie той моделью, которую попросил вызывающий код. Если она не ответила,
следующая модель Kie, затем прямой Gemini, Grok и Cloudflare — только если
ключ задан. Удачная модель возвращается сразу. Закрытый канал не спрашиваем
снова несколько часов. Если не ответил никто, песню не из чего писать.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests

from backend.logger import log
from backend.services.kie_client import KieClient
from backend.services.llm_signal import record_all_failed, record_backup_used, record_recovery
from backend.services.openai_chat_client import OpenaiChatClient
from backend.settings import (
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_API_TOKEN,
    CLOUDFLARE_GATEWAY_ID,
    CLOUDFLARE_MODELS,
    GEMINI_API_KEY,
    GEMINI_MODELS,
    KIE_API_KEY,
    KIE_MODELS,
    XAI_API_KEY,
    XAI_MODELS,
)

USER_LYRICS_FAIL_MESSAGE = (
    "Не получилось написать текст песни. Попытка не списана. Нажмите ещё раз."
)

_DEAD_FOR = {
    "gone": timedelta(hours=6),
    "maintenance": timedelta(minutes=15),
    "timeout": timedelta(minutes=10),
}
_LOCK = threading.Lock()
_DEAD: dict[tuple[str, str], datetime] = {}


class LlmUnavailable(RuntimeError):
    """Ни одна текстовая модель не ответила."""


@dataclass
class _Step:
    provider: str
    model: str
    kind: str
    client: KieClient | OpenaiChatClient
    kie_model: str = ""


@dataclass
class LlmChain:
    """Тот же complete(), что у одного клиента. MODEL_* сохранены для старых вызовов."""

    MODEL_PRO: str = "yandexgpt"
    MODEL_LITE: str = "yandexgpt-lite"
    _kie: KieClient = field(default_factory=KieClient)
    _steps_backup: list[_Step] = field(default_factory=list)

    def complete(
        self,
        system_prompt: str,
        user_text: str,
        *,
        max_tokens: int = 400,
        temperature: float = 0.7,
        model: str = MODEL_LITE,
    ) -> str:
        steps = self._ordered_steps(model)
        if not steps:
            raise LlmUnavailable(USER_LYRICS_FAIL_MESSAGE)
        live = [step for step in steps if not _is_dead(step.provider, step.model)]
        if not live:
            first = steps[0]
            record_all_failed(provider=first.provider, model=first.model, reason="gone")
            raise LlmUnavailable(USER_LYRICS_FAIL_MESSAGE)
        errors: list[tuple[_Step, str]] = []
        for index, step in enumerate(live):
            timeout = 90 if index == 0 else 45
            try:
                text = self._call(
                    step,
                    system_prompt,
                    user_text,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=timeout,
                )
            except Exception as exc:
                kind = _classify(exc)
                _mark_dead(step.provider, step.model, kind)
                errors.append((step, kind))
                log.warning(
                    "LLM %s/%s failed (%s): %s",
                    step.provider,
                    step.model,
                    kind,
                    exc,
                )
                continue
            self._after_success(step, errors, steps)
            return text
        last = errors[-1]
        record_all_failed(provider=last[0].provider, model=last[0].model, reason=last[1])
        raise LlmUnavailable(USER_LYRICS_FAIL_MESSAGE)

    def _ordered_steps(self, requested_model: str) -> list[_Step]:
        steps: list[_Step] = []
        if KIE_API_KEY:
            first = self._kie._resolve_slug(requested_model)
            slugs: list[str] = []
            for slug in [first, *KIE_MODELS]:
                if slug and slug not in slugs:
                    slugs.append(slug)
            for slug in slugs:
                steps.append(
                    _Step(provider="Kie", model=slug, kind="kie", client=self._kie, kie_model=slug)
                )
        steps.extend(self._steps_backup)
        return steps

    @staticmethod
    def _call(
        step: _Step,
        system_prompt: str,
        user_text: str,
        *,
        max_tokens: int,
        temperature: float,
        timeout: int,
    ) -> str:
        if step.kind == "kie":
            return step.client.complete(  # type: ignore[union-attr]
                system_prompt,
                user_text,
                model=step.kie_model,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
            )
        return step.client.complete(  # type: ignore[union-attr]
            system_prompt,
            user_text,
            model=step.model,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )

    @staticmethod
    def _after_success(
        step: _Step,
        errors: list[tuple[_Step, str]],
        steps: list[_Step],
    ) -> None:
        _clear_dead(step.provider, step.model)
        asked = steps[0]
        if step.provider == asked.provider and step.model == asked.model and not errors:
            if KIE_MODELS and step.model == KIE_MODELS[0]:
                record_recovery(provider=step.provider, model=step.model)
            return
        if errors:
            failed, reason = errors[0]
        else:
            failed, reason = asked, "gone"
        record_backup_used(
            provider=failed.provider,
            model=failed.model,
            reason=reason,
            saved_by=f"{step.provider} {step.model}",
        )


def build_llm_chain() -> LlmChain:
    chain = LlmChain()
    chain._steps_backup = _backup_steps()
    return chain


def clear_dead_models() -> None:
    with _LOCK:
        _DEAD.clear()


def _backup_steps() -> list[_Step]:
    steps: list[_Step] = []
    if GEMINI_API_KEY:
        client = OpenaiChatClient(
            name="Gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key=GEMINI_API_KEY,
        )
        for model in GEMINI_MODELS:
            steps.append(_Step(provider="Gemini", model=model, kind="openai", client=client))
    if XAI_API_KEY:
        client = OpenaiChatClient(
            name="Grok",
            base_url="https://api.x.ai/v1",
            api_key=XAI_API_KEY,
        )
        for model in XAI_MODELS:
            steps.append(_Step(provider="Grok", model=model, kind="openai", client=client))
    if CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID:
        client = OpenaiChatClient(
            name="Cloudflare",
            base_url=(
                "https://api.cloudflare.com/client/v4/accounts/"
                f"{CLOUDFLARE_ACCOUNT_ID}/ai/v1"
            ),
            api_key=CLOUDFLARE_API_TOKEN,
            extra_headers={"cf-aig-gateway-id": CLOUDFLARE_GATEWAY_ID or "default"},
        )
        for model in CLOUDFLARE_MODELS:
            steps.append(_Step(provider="Cloudflare", model=model, kind="openai", client=client))
    elif CLOUDFLARE_API_TOKEN and not CLOUDFLARE_ACCOUNT_ID:
        log.warning("Cloudflare token is set, account id is empty — provider skipped")
    return steps


def _classify(exc: Exception) -> str:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return "timeout"
    text = str(exc).lower()
    if "timed out" in text or "timeout" in text:
        return "timeout"
    if any(
        phrase in text
        for phrase in (
            "channel is not supported",
            "model not found",
            "no such model",
            "does not exist",
            "unknown model",
            "not found",
        )
    ):
        return "gone"
    if any(phrase in text for phrase in ("maintained", "try again later", "maintenance", "unavailable")):
        return "maintenance"
    return "other"


def _is_dead(provider: str, model: str) -> bool:
    with _LOCK:
        until = _DEAD.get((provider, model))
        if until is None:
            return False
        if datetime.now(timezone.utc) >= until:
            _DEAD.pop((provider, model), None)
            return False
        return True


def _mark_dead(provider: str, model: str, kind: str) -> None:
    delay = _DEAD_FOR.get(kind)
    if delay is None:
        return
    with _LOCK:
        _DEAD[(provider, model)] = datetime.now(timezone.utc) + delay


def _clear_dead(provider: str, model: str) -> None:
    with _LOCK:
        _DEAD.pop((provider, model), None)
