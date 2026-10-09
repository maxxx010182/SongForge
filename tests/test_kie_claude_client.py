"""Claude на Kie ходит в /anthropic/v1/messages и не шлёт temperature.

gpt-5-2 остаётся в адресе chat/completions и не подменяется на Gemini.
"""

from backend.services.kie_claude_client import KieClaudeClient
from backend.services.kie_client import KieClient
import backend.services.kie_claude_client as claude_module
import backend.services.kie_client as kie_module


class _Response:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


def test_claude_letter_matches_the_verse_probe(monkeypatch):
    captured: dict = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["body"] = json
        captured["timeout"] = timeout
        return _Response(
            {"content": [{"type": "thinking", "text": "скрыто"}, {"type": "text", "text": "[Куплет]\nмама"}]}
        )

    monkeypatch.setattr(claude_module.requests, "post", fake_post)
    monkeypatch.setattr(claude_module, "KIE_API_KEY", "test-key")
    text = KieClaudeClient().complete(
        "система",
        "песня маме",
        model="claude-sonnet-5-5",
        max_tokens=3500,
        temperature=0.8,
        timeout=32,
    )
    assert text == "[Куплет]\nмама"
    assert captured["url"].endswith("/anthropic/v1/messages")
    assert captured["body"]["model"] == "claude-sonnet-5-5"
    assert captured["body"]["stream"] is False
    assert captured["body"]["system"] == "система"
    assert captured["body"]["messages"] == [{"role": "user", "content": "песня маме"}]
    assert "temperature" not in captured["body"]
    assert captured["timeout"] == 32


def test_gpt_slug_is_not_rewritten_to_gemini(monkeypatch):
    captured: dict = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["body"] = json
        return _Response({"choices": [{"message": {"content": "куплет"}}]})

    monkeypatch.setattr(kie_module.requests, "post", fake_post)
    monkeypatch.setattr(kie_module, "KIE_API_KEY", "test-key")
    text = KieClient().complete(
        "система",
        "песня",
        model="gpt-5-2",
        max_tokens=3500,
        temperature=0.7,
        timeout=16,
    )
    assert text == "куплет"
    assert captured["url"].endswith("/gpt-5-2/v1/chat/completions")
    assert "reasoning_effort" not in captured["body"]
