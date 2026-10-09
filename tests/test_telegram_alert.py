"""Техбот: пустые настройки молчат, удачный ответ уходит одним сообщением."""

import backend.services.telegram_alert as telegram_alert


class _Response:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_send_alert_skips_without_token(monkeypatch):
    monkeypatch.setattr(telegram_alert, "TELEGRAM_ALERT_BOT_TOKEN", "")
    monkeypatch.setattr(telegram_alert, "TELEGRAM_ALERT_CHAT_ID", "1")
    called = {"n": 0}

    def post(*args, **kwargs):
        called["n"] += 1
        return _Response(200, {"ok": True})

    monkeypatch.setattr(telegram_alert.requests, "post", post)
    assert telegram_alert.send_alert("Тексты не пишутся") is False
    assert called["n"] == 0


def test_send_alert_posts_once(monkeypatch):
    monkeypatch.setattr(telegram_alert, "TELEGRAM_ALERT_BOT_TOKEN", "secret-token")
    monkeypatch.setattr(telegram_alert, "TELEGRAM_ALERT_CHAT_ID", "42")
    seen = {}

    def post(url, json, timeout):
        seen["url"] = url
        seen["json"] = json
        seen["timeout"] = timeout
        return _Response(200, {"ok": True})

    monkeypatch.setattr(telegram_alert.requests, "post", post)
    assert telegram_alert.send_alert("Тексты не пишутся") is True
    assert seen["url"].endswith("/sendMessage")
    assert "secret-token" not in seen["json"]["text"]
    assert seen["json"]["chat_id"] == "42"
    assert seen["json"]["text"] == "Тексты не пишутся"
    assert seen["timeout"] == 5


def test_lyric_signal_reaches_telegram_without_max(monkeypatch):
    import backend.services.llm_signal as llm_signal

    sent = []
    monkeypatch.setattr(llm_signal, "ADMIN_MAX_USER_ID", "")
    monkeypatch.setattr(telegram_alert, "send_alert", lambda text: sent.append(text) or True)
    llm_signal._notify("Тексты не пишутся")
    assert sent == ["Тексты не пишутся"]
