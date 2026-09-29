"""Очередь текстовых моделей: запасной ключ, мёртвый канал, отказ без заготовки."""

from backend.models import ProductionPlan
from backend.services.llm_chain import (
    LlmChain,
    LlmUnavailable,
    _Step,
    clear_dead_models,
)
from backend.services.prompt_builder import PromptBuilder
import backend.services.llm_chain as llm_chain
import backend.services.llm_signal as llm_signal


class _Kie:
    def __init__(self, fail: bool = True) -> None:
        self.calls: list[str] = []
        self.fail = fail

    def _resolve_slug(self, model: str) -> str:
        if model in {"yandexgpt", "pro", "gemini-3.1-pro"}:
            return "gemini-3.1-pro"
        return "gemini-3-pro"

    def complete(self, system_prompt, user_text, *, model, max_tokens, temperature, timeout):
        self.calls.append(model)
        if self.fail:
            raise RuntimeError("The channel is not supported")
        return "Текст от Kie " + user_text[:20]


class _Spare:
    def __init__(self, text: str = "Припев про маму и май") -> None:
        self.calls: list[str] = []
        self.text = text

    def complete(self, system_prompt, user_text, *, model, max_tokens, temperature, timeout):
        self.calls.append(model)
        if not self.text:
            raise RuntimeError("model not found")
        return self.text


def _chain(monkeypatch, tmp_path, kie, spare):
    monkeypatch.setattr(llm_signal, "_PATH", tmp_path / "llm_signal.json")
    monkeypatch.setattr(llm_signal, "_notify", lambda text: None)
    monkeypatch.setattr(llm_chain, "KIE_API_KEY", "test-key")
    monkeypatch.setattr(llm_chain, "KIE_MODELS", ["gemini-3.1-pro", "gemini-3-pro"])
    clear_dead_models()
    chain = LlmChain()
    chain._kie = kie
    chain._steps_backup = [
        _Step(provider="Grok", model="grok-4.7", kind="openai", client=spare)
    ]
    return chain


def test_dead_kie_uses_grok(monkeypatch, tmp_path):
    kie = _Kie()
    spare = _Spare()
    chain = _chain(monkeypatch, tmp_path, kie, spare)
    text = chain.complete("sys", "песня маме", model=chain.MODEL_PRO)
    assert text == "Припев про маму и май"
    assert kie.calls[0] == "gemini-3.1-pro"
    assert spare.calls == ["grok-4.7"]
    alert = llm_signal.current_alert()
    assert alert is not None
    assert "Grok" in alert["message"]
    assert alert["level"] == "warning"


def test_all_providers_down_raises_without_waiting_twice(monkeypatch, tmp_path):
    kie = _Kie()
    spare = _Spare(text="")
    chain = _chain(monkeypatch, tmp_path, kie, spare)
    try:
        chain.complete("sys", "песня маме", model=chain.MODEL_PRO)
        raise AssertionError("must fail")
    except LlmUnavailable as exc:
        assert "Попытка не списана" in str(exc)
    # Канал Kie помечен мёртвым: второй запрос его не трогает.
    kie.calls.clear()
    spare.calls.clear()
    try:
        chain.complete("sys", "ещё раз", model=chain.MODEL_PRO)
    except LlmUnavailable:
        pass
    assert "gemini-3.1-pro" not in kie.calls
    alert = llm_signal.current_alert()
    assert alert is not None
    assert alert["level"] == "critical"


def test_lyrics_do_not_fall_back_to_canned_song():
    class Boom:
        MODEL_PRO = "yandexgpt"
        MODEL_LITE = "yandexgpt-lite"

        def complete(self, *args, **kwargs):
            raise RuntimeError("down")

    builder = PromptBuilder(Boom())
    try:
        builder.generate_lyrics("песня про папу", ProductionPlan())
        raise AssertionError("must fail")
    except ValueError as exc:
        assert "Держи меня" not in str(exc)
        assert "Ночь ложится" not in str(exc)
        assert "Попытка не списана" in str(exc)
