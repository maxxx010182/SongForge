"""Воронка MAX: ворота, brief, вход по ссылке."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import app
from backend.database.db import get_connection, init_db
from backend.services.auth_service import AuthService
from backend.services.consultant import ConsultantService
from backend.services.max_bot import MaxBot
from backend.services.messenger_service import MessengerService, compose_brief, webhook_secret
from backend.services.rate_limit import limiter


class FakeApi:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.callbacks: list[str] = []

    def configured(self) -> bool:
        return True

    def send_message(self, *, user_id, text, buttons=None, image_url=None) -> bool:
        self.sent.append(
            {
                "user_id": str(user_id),
                "text": text,
                "buttons": buttons or [],
                "image_url": image_url,
            }
        )
        return True

    def answer_callback(self, callback_id: str, *, notification: str = "") -> bool:
        self.callbacks.append(callback_id)
        return True


def _uid() -> str:
    return str(900000000 + uuid.uuid4().int % 100000000)


def _cleanup(max_user_id: str) -> None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, user_id FROM messenger_contacts WHERE max_user_id = ?",
            (max_user_id,),
        ).fetchone()
        if not row:
            return
        conn.execute("DELETE FROM messenger_consents WHERE contact_id = ?", (row["id"],))
        conn.execute("DELETE FROM messenger_contacts WHERE id = ?", (row["id"],))
        if row["user_id"]:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["user_id"],))
            conn.execute(
                "DELETE FROM auth_identities WHERE user_id = ? AND provider = 'max'",
                (row["user_id"],),
            )
            conn.execute("DELETE FROM users WHERE id = ?", (row["user_id"],))


def _bot() -> tuple[MaxBot, FakeApi, str]:
    init_db()
    limiter.reset()
    max_user_id = _uid()
    api = FakeApi()
    bot = MaxBot(api=api, messenger=MessengerService(), auth=AuthService())
    return bot, api, max_user_id


def _cb(bot: MaxBot, max_user_id: str, payload: str, name: str | None = None) -> None:
    name = name or f"tmax_{max_user_id}"
    bot.handle_update(
        {
            "update_type": "message_callback",
            "callback": {
                "callback_id": payload,
                "payload": payload,
                "user": {"user_id": int(max_user_id), "name": name},
            },
        }
    )


def test_compose_brief():
    assert compose_brief("маме", "день рождения") == "Песня маме. День рождения."
    assert compose_brief("себе", "") == "Песня себе."


def test_gate_on_bot_started():
    bot, api, max_user_id = _bot()
    try:
        bot.handle_update(
            {
                "update_type": "bot_started",
                "chat_id": int(max_user_id),
                "user": {"user_id": int(max_user_id), "name": f"tmax_{max_user_id}"},
            }
        )
        assert api.sent
        assert "стоп" in api.sent[0]["text"].lower()
        assert "проба" in api.sent[0]["text"].lower()
        assert api.sent[0]["image_url"]
        assert api.sent[0]["image_url"].endswith("/assets/max-cover.jpg")
        labels = [
            btn.get("text")
            for row in api.sent[0]["buttons"]
            for btn in row
        ]
        payloads = [
            btn.get("payload")
            for row in api.sent[0]["buttons"]
            for btn in row
        ]
        assert "Поехали" in labels
        assert "accept" in payloads
    finally:
        _cleanup(max_user_id)


def test_accept_whom_mood_sends_studio_link():
    bot, api, max_user_id = _bot()
    try:
        bot.handle_update(
            {
                "update_type": "bot_started",
                "user": {"user_id": int(max_user_id), "name": f"tmax_{max_user_id}"},
                "chat_id": int(max_user_id),
            }
        )
        _cb(bot, max_user_id, "accept")
        _cb(bot, max_user_id, "whom:mom")
        _cb(bot, max_user_id, "mood:birthday")
        last = api.sent[-1]
        assert "маме" in last["text"].lower()
        assert "день рождения" in last["text"].lower()
        urls = [
            btn.get("url", "")
            for row in last["buttons"]
            for btn in row
        ]
        assert any("/api/auth/max?m=" in url for url in urls)
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["brief"].startswith("Песня маме")
        assert contact["occasion_key"] == "birthday"
        assert contact["next_nudge_at"]
        assert contact["user_id"]
        assert contact["messages_ok"] == 1
    finally:
        _cleanup(max_user_id)


def test_stop_command():
    bot, api, max_user_id = _bot()
    try:
        bot.handle_update(
            {
                "update_type": "message_callback",
                "callback": {
                    "callback_id": "cb1",
                    "payload": "accept",
                    "user": {"user_id": int(max_user_id), "name": f"tmax_{max_user_id}"},
                },
            }
        )
        bot.handle_update(
            {
                "update_type": "message_created",
                "message": {
                    "sender": {"user_id": int(max_user_id), "is_bot": False, "name": f"tmax_{max_user_id}"},
                    "recipient": {"chat_type": "dialog", "user_id": int(max_user_id)},
                    "body": {"text": "стоп"},
                },
            }
        )
        assert "молчу" in api.sent[-1]["text"].lower()
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["funnel_stage"] == "stopped"
        assert contact["messages_ok"] == 0
    finally:
        _cleanup(max_user_id)


def test_free_text_whom():
    bot, api, max_user_id = _bot()
    try:
        _cb(bot, max_user_id, "accept")
        bot.handle_update(
            {
                "update_type": "message_created",
                "message": {
                    "sender": {"user_id": int(max_user_id), "is_bot": False, "name": f"tmax_{max_user_id}"},
                    "recipient": {"chat_type": "dialog", "user_id": int(max_user_id)},
                    "body": {"text": "бабушке"},
                },
            }
        )
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["brief_whom"] == "бабушке"
        assert "повод" in api.sent[-1]["text"].lower()
    finally:
        _cleanup(max_user_id)


def test_login_token_and_me_brief():
    init_db()
    limiter.reset()
    max_user_id = _uid()
    bot, api, _ = _bot()
    bot_user = max_user_id
    try:
        _cb(bot, bot_user, "accept")
        _cb(bot, bot_user, "whom:mom")
        _cb(bot, bot_user, "mood:birthday")
        contact = MessengerService().get_by_max(bot_user)
        token = MessengerService().make_login_token(contact["id"])
        client = TestClient(app)
        res = client.get(f"/api/auth/max?m={token}", follow_redirects=False)
        assert res.status_code in {302, 307}
        assert "auth=ok" in res.headers.get("location", "")
        me = client.get("/api/me")
        assert me.status_code == 200
        data = me.json()
        assert data["logged_in"] is True
        assert "маме" in data["messenger_brief"].lower()
    finally:
        _cleanup(bot_user)


def test_greeting_keeps_whom_step():
    bot, api, max_user_id = _bot()
    try:
        _cb(bot, max_user_id, "accept")
        bot.handle_update(
            {
                "update_type": "message_created",
                "message": {
                    "sender": {
                        "user_id": int(max_user_id),
                        "is_bot": False,
                        "name": f"tmax_{max_user_id}",
                    },
                    "recipient": {"chat_type": "dialog", "user_id": int(max_user_id)},
                    "body": {"text": "привет"},
                },
            }
        )
        last = api.sent[-1]
        assert "кому" in last["text"].lower()
        payloads = [btn.get("payload") or "" for row in last["buttons"] for btn in row]
        assert "whom:mom" in payloads
        assert "segment:business" not in payloads
    finally:
        _cleanup(max_user_id)


def test_business_branch_sends_studio_brief():
    bot, api, max_user_id = _bot()
    try:
        _cb(bot, max_user_id, "accept")
        bot.handle_update(
            {
                "update_type": "message_created",
                "message": {
                    "sender": {
                        "user_id": int(max_user_id),
                        "is_bot": False,
                        "name": f"tmax_{max_user_id}",
                    },
                    "recipient": {"chat_type": "dialog", "user_id": int(max_user_id)},
                    "body": {"text": "для рекламы бренда"},
                },
            }
        )
        _cb(bot, max_user_id, "bizgoal:jingle")
        _cb(bot, max_user_id, "biztone:light")
        last = api.sent[-1]
        assert "джингл" in last["text"].lower()
        assert "юмором" in last["text"].lower()
        assert "два варианта" in last["text"].lower()
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["segment"] == "business"
        assert contact["brief"].startswith("Для бизнеса")
        urls = [btn.get("url", "") for row in last["buttons"] for btn in row]
        assert any("/api/auth/max?m=" in url for url in urls)
    finally:
        _cleanup(max_user_id)


def test_webhook_rejects_bad_secret():
    client = TestClient(app)
    with patch("backend.app.MAX_BOT_TOKEN", "test-token"), patch(
        "backend.app.webhook_secret", return_value="secret123"
    ):
        res = client.post(
            "/api/webhooks/max",
            json={"update_type": "bot_started"},
            headers={"X-Max-Bot-Api-Secret": "wrong"},
        )
        assert res.status_code == 403


def test_consultant_includes_brief():
    captured = {}

    def fake_complete(system, user_text, **kwargs):
        captured["user"] = user_text
        return "Ок, продолжим с этой идеей."

    svc = ConsultantService()
    svc._llm.complete = fake_complete  # type: ignore[method-assign]
    reply = svc.reply("как создать?", brief="Песня маме. Тепло.")
    assert "маме" in captured["user"]
    assert reply


def test_webhook_secret_stable():
    with patch("backend.services.messenger_service.MAX_BOT_TOKEN", "abc"), patch(
        "backend.services.messenger_service.MAX_WEBHOOK_SECRET", ""
    ):
        a = webhook_secret()
        b = webhook_secret()
        assert a == b
        assert len(a) >= 5


def _force_nudge_due(contact_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE messenger_contacts SET next_nudge_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", contact_id),
        )


def test_nudge_three_steps_then_silence():
    bot, api, max_user_id = _bot()
    try:
        _cb(bot, max_user_id, "accept")
        _cb(bot, max_user_id, "whom:mom")
        _cb(bot, max_user_id, "mood:birthday")
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["nudge_step"] == 0
        assert contact["next_nudge_at"]
        api.sent.clear()
        assert bot.process_due_nudges() == 0
        assert api.sent == []

        _force_nudge_due(contact["id"])
        assert bot.process_due_nudges() == 1
        assert "черновик на месте" in api.sent[-1]["text"].lower()
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["nudge_step"] == 1

        _force_nudge_due(contact["id"])
        assert bot.process_due_nudges() == 1
        assert "крутилка" in api.sent[-1]["text"].lower()
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["nudge_step"] == 2

        _force_nudge_due(contact["id"])
        assert bot.process_due_nudges() == 1
        last = api.sent[-1]
        assert "отложим" in last["text"].lower()
        assert "стоп" in last["text"].lower()
        payloads = [btn.get("payload") for row in last["buttons"] for btn in row]
        assert "stop_nudge" in payloads
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["nudge_step"] == 3
        assert not contact["next_nudge_at"]

        api.sent.clear()
        assert bot.process_due_nudges() == 0
        assert api.sent == []
    finally:
        _cleanup(max_user_id)


def test_nudge_skips_stopped():
    bot, api, max_user_id = _bot()
    try:
        _cb(bot, max_user_id, "accept")
        _cb(bot, max_user_id, "whom:mom")
        _cb(bot, max_user_id, "mood:just")
        contact = MessengerService().get_by_max(max_user_id)
        MessengerService().stop(contact)
        _force_nudge_due(contact["id"])
        api.sent.clear()
        assert bot.process_due_nudges() == 0
        assert api.sent == []
    finally:
        _cleanup(max_user_id)


def test_studio_open_skips_two_hour_nudge():
    bot, api, max_user_id = _bot()
    try:
        _cb(bot, max_user_id, "accept")
        _cb(bot, max_user_id, "whom:mom")
        _cb(bot, max_user_id, "mood:holiday")
        svc = MessengerService()
        contact = svc.get_by_max(max_user_id)
        first = contact["next_nudge_at"]
        contact = svc.note_studio_opened(contact)
        later = contact["next_nudge_at"]
        assert later > first
        api.sent.clear()
        assert bot.process_due_nudges() == 0
    finally:
        _cleanup(max_user_id)
