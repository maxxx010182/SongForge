"""Очередь текстовых моделей.

Песня: Gemini 3 Pro, при ошибке Gemini 3.1 Pro, при новой ошибке GPT 5.2.
Сонет не вызываем. Следующую модель зовём только если предыдущая вернула
ошибку, а не если она ещё пишет. Короткий разбор идеи — один вызов первой
модели. Прямой Gemini с этого сервера не вызываем.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests

from backend.logger import log
from backend.services.kie_claude_client import KieClaudeClient
from backend.services.kie_client import KieClient
from backend.services.llm_signal import record_all_failed, record_backup_used, record_recovery
from backend.services.openai_chat_client import OpenaiChatClient
from backend.settings import (
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_API_TOKEN,
    CLOUDFLARE_GATEWAY_ID,
    CLOUDFLARE_MODELS,
    GEMINI_API_KEY,
    KIE_API_KEY,
    KIE_CLAUDE_MODELS,
    KIE_MODELS,
    XAI_API_KEY,
    XAI_MODELS,
)

# Запасную модель не стартуем по таймеру: оборванный запрос Kie всё равно дописывает и берёт деньги.
_SONG_TIMEOUT = 120
_RESERVE_TIMEOUT = 90
_SHORT_TIMEOUT = 20

USER_LYRICS_FAIL_MESSAGE = (
    "Не получилось написать текст песни. Попытка не списана. Нажмите ещё раз."
)

# Таймаут не закрывает модель: она могла дописать ответ уже после нашего обрыва.
_DEAD_FOR = {
    "gone": timedelta(hours=6),
    "maintenance": timedelta(minutes=15),
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
    client: KieClient | KieClaudeClient | OpenaiChatClient
    kie_model: str = ""


@dataclass
class LlmChain:
    """Тот же complete(), что у одного клиента. MODEL_* сохранены для старых вызовов."""

    MODEL_PRO: str = "yandexgpt"
    MODEL_LITE: str = "yandexgpt-lite"
    _kie: KieClient = field(default_factory=KieClient)
    _claude: KieClaudeClient = field(default_factory=KieClaudeClient)
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
        pro = self._is_pro(model)
        for index, step in enumerate(live):
            if pro and index == 0:
                timeout = _SONG_TIMEOUT
            elif pro:
                timeout = _RESERVE_TIMEOUT
            else:
                timeout = _SHORT_TIMEOUT
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
                if kind != "timeout":
                    _mark_dead(step.provider, step.model, kind)
                errors.append((step, kind))
                log.warning(
                    "LLM %s/%s failed (%s): %s",
                    step.provider,
                    step.model,
                    kind,
                    exc,
                )
                if kind == "timeout":
                    log.warning(
                        "LLM %s/%s still writing after %ss; next model is not called",
                        step.provider,
                        step.model,
                        timeout,
                    )
                    break
                continue
            self._after_success(step, errors, steps)
            return text
        if not errors:
            first = live[0]
            record_all_failed(provider=first.provider, model=first.model, reason="timeout")
            raise LlmUnavailable(USER_LYRICS_FAIL_MESSAGE)
        last = errors[-1]
        record_all_failed(provider=last[0].provider, model=last[0].model, reason=last[1])
        raise LlmUnavailable(USER_LYRICS_FAIL_MESSAGE)

    def _is_pro(self, requested_model: str) -> bool:
        return (requested_model or "").strip() in {
            self.MODEL_PRO,
            "yandexgpt",
            "pro",
            "lyrics",
        }

    def _ordered_steps(self, requested_model: str) -> list[_Step]:
        steps: list[_Step] = []
        pro = self._is_pro(requested_model)
        if KIE_API_KEY:
            seen: list[str] = []
            if pro:
                names = [*KIE_CLAUDE_MODELS, *KIE_MODELS]
            else:
                # Разбор идеи — один короткий ответ первой модели. Вторая здесь не нужна.
                names = KIE_MODELS[:1]
            for name in names:
                if not name or name in seen:
                    continue
                seen.append(name)
                if name in KIE_CLAUDE_MODELS and pro:
                    steps.append(
                        _Step(provider="Kie", model=name, kind="claude", client=self._claude)
                    )
                    continue
                steps.append(
                    _Step(
                        provider="Kie",
                        model=name,
                        kind="kie",
                        client=self._kie,
                        kie_model=name,
                    )
                )
        if pro:
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
    # Ключ прямого Gemini остаётся в .env. С сервера в РФ он отвечает квотой
    # или отказом по стране и только отнимает время до Cloudflare.
    if GEMINI_API_KEY:
        log.info("Direct Gemini key is set; this server does not call it")
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
