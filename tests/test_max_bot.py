"""Воронка MAX: ворота, brief, вход по ссылке."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import app
from backend.database.db import get_connection, init_db
from backend.services.auth_service import AuthService
from backend.services.consultant import ConsultantService
from backend.services.max_bot import MaxBot
from backend.services.messenger_service import MessengerService, compose_brief, webhook_secret
from backend.services.nudge_schedule import evening_after
from backend.services.rate_limit import limiter


class FakeApi:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.callbacks: list[str] = []
        self.deleted: list[str] = []
        self.edited: list[dict] = []

    def configured(self) -> bool:
        return True

    def send_message(
        self,
        *,
        user_id,
        text,
        buttons=None,
        image_url=None,
        image_payload=None,
        format=None,
    ):
        mid = f"m{len(self.sent) + 1}"
        self.sent.append(
            {
                "user_id": str(user_id),
                "text": text,
                "buttons": buttons or [],
                "image_url": image_url,
                "image_payload": image_payload,
                "format": format,
                "mid": mid,
            }
        )
        return {"message": {"body": {"mid": mid}}}

    def edit_message(self, message_id, *, text, buttons=None, format=None):
        self.edited.append(
            {"mid": message_id, "text": text, "buttons": buttons or []}
        )
        return {"message": {"body": {"mid": message_id}}}

    def delete_message(self, message_id) -> bool:
        self.deleted.append(str(message_id))
        return True

    def get_cover_payload(self):
        return None

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
        conn.execute("DELETE FROM messenger_followups WHERE contact_id = ?", (row["id"],))
        conn.execute("DELETE FROM messenger_consents WHERE contact_id = ?", (row["id"],))
        conn.execute("DELETE FROM messenger_contacts WHERE id = ?", (row["id"],))
        if row["user_id"]:
            conn.execute("DELETE FROM generations WHERE user_id = ?", (row["user_id"],))
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


def _text(bot: MaxBot, max_user_id: str, text: str, name: str | None = None) -> None:
    name = name or f"tmax_{max_user_id}"
    bot.handle_update(
        {
            "update_type": "message_created",
            "message": {
                "sender": {
                    "user_id": int(max_user_id),
                    "is_bot": False,
                    "name": name,
                },
                "recipient": {"chat_type": "dialog", "user_id": int(max_user_id)},
                "body": {"text": text},
            },
        }
    )


def _finish_gift(
    bot: MaxBot,
    max_user_id: str,
    *,
    whom: str = "whom:mom",
    occasion: str = "occasion:birthday",
) -> None:
    _cb(bot, max_user_id, "accept")
    _cb(bot, max_user_id, whom)
    _cb(bot, max_user_id, occasion)
    _cb(bot, max_user_id, "detail:skip")
    _cb(bot, max_user_id, "genre:pop")
    _cb(bot, max_user_id, "sound:uplifting")
    _cb(bot, max_user_id, "voice:female")
    _cb(bot, max_user_id, "confirm:ok")


def test_compose_brief():
    text = compose_brief("маме", "день рождения")
    assert "маме" in text.lower()
    assert "день рождения" in text.lower()
    assert "кому:" not in text.lower()
    rich = compose_brief(
        "маме",
        "день рождения",
        detail="свет на кухне",
        sound="спокойно",
        voice="женский",
        genre="Поп",
    )
    assert "свет на кухне" in rich
    assert "женский" in rich.lower()
    assert "поп" in rich.lower()
    self_song = compose_brief("", "про коня в поле", plot="just")
    assert "коня" in self_song.lower()
    assert "не указан" not in self_song.lower()


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
        first = api.sent[0]["text"].lower()
        assert "стоп" not in first
        assert "мурашек" in first or "говорится" in first
        assert "нажимая" not in first
        assert "оферт" not in first
        labels = [btn.get("text") for row in api.sent[0]["buttons"] for btn in row]
        payloads = [
            btn.get("payload") or ""
            for row in api.sent[0]["buttons"]
            for btn in row
        ]
        assert "legal:offer:1" not in payloads
        assert "вернитесь" not in first
        assert any("услышать" in (t or "").lower() for t in labels)
        assert api.sent[0]["image_url"] or api.sent[0]["image_payload"]
        if api.sent[0]["image_url"]:
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
        assert any("услышать" in (t or "").lower() for t in labels)
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
        _finish_gift(bot, max_user_id)
        last = api.sent[-1]
        assert "маме" in last["text"].lower()
        assert "день рождения" in last["text"].lower()
        joined = " ".join(
            btn.get("text", "") for row in last["buttons"] for btn in row
        ).lower()
        assert "песней" in joined or "вперёд" in joined
        urls = [
            btn.get("url", "")
            for row in last["buttons"]
            for btn in row
        ]
        assert any("/api/auth/max?m=" in url for url in urls)
        last_text = last["text"].lower()
        assert "открывая студию или документы" in last_text
        assert "/api/auth/max?m=" in last["text"]
        assert "next=" in last["text"]
        assert "legal/terms" in last["text"]
        assert "legal/privacy" in last["text"]
        assert "legal/offer" in last["text"]
        contact = MessengerService().get_by_max(max_user_id)
        assert "маме" in contact["brief"].lower()
        assert "женский" in contact["brief"].lower()
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
        assert "привет" not in contact["brief"].lower()
        last = api.sent[-1]["text"].lower()
        assert "дате" in last or "сердца" in last or "повод" in last
    finally:
        _cleanup(max_user_id)


def test_login_token_and_me_brief():
    init_db()
    limiter.reset()
    max_user_id = _uid()
    bot, api, _ = _bot()
    bot_user = max_user_id
    try:
        _finish_gift(bot, bot_user)
        contact = MessengerService().get_by_max(bot_user)
        token = MessengerService().make_login_token(contact["id"])
        client = TestClient(app)
        res = client.get(f"/api/auth/max?m={token}", follow_redirects=False)
        assert res.status_code in {302, 307}
        assert "auth=ok" in res.headers.get("location", "")
        me = client.get("/api/me?tz=Asia/Vladivostok")
        assert me.status_code == 200
        data = me.json()
        assert data["logged_in"] is True
        assert "маме" in data["messenger_brief"].lower()
        contact = MessengerService().get_by_max(bot_user)
        assert contact["tz_name"] == "Asia/Vladivostok"
        assert contact["last_site_at"]
        res2 = client.get(
            f"/api/auth/max?m={token}&next=/legal/offer",
            follow_redirects=False,
        )
        assert res2.status_code in {302, 307}
        assert res2.headers.get("location", "").endswith("/legal/offer")
        res3 = client.get(
            f"/api/auth/max?m={token}&next=https://evil.example/",
            follow_redirects=False,
        )
        assert "evil" not in (res3.headers.get("location") or "")
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
        assert "кого" in last["text"].lower()
        payloads = [btn.get("payload") or "" for row in last["buttons"] for btn in row]
        assert "whom:mom" in payloads
        assert "segment:business" not in payloads
        contact = MessengerService().get_by_max(max_user_id)
        assert (contact.get("brief_whom") or "") == ""
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
        _cb(bot, max_user_id, "bizgoal:ads")
        _cb(bot, max_user_id, "bizdetail:skip")
        _cb(bot, max_user_id, "biztone:friendly")
        last = api.sent[-1]
        assert "реклам" in last["text"].lower() or "собрал" in last["text"].lower()
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["segment"] == "business"
        assert "бизнес" in contact["brief"].lower()
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


def test_nudge_three_steps_then_weekly():
    bot, api, max_user_id = _bot()
    try:
        _finish_gift(bot, max_user_id)
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["nudge_step"] == 0
        assert contact["next_nudge_at"]
        api.sent.clear()
        assert bot.process_due_nudges() == 0
        assert api.sent == []

        _force_nudge_due(contact["id"])
        assert bot.process_due_nudges() == 1
        assert "черновик уже в студии" in api.sent[-1]["text"].lower()
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["nudge_step"] == 1

        _force_nudge_due(contact["id"])
        assert bot.process_due_nudges() == 1
        assert "черновик ждёт в студии" in api.sent[-1]["text"].lower() or "не вышло зайти" in api.sent[-1]["text"].lower()
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["nudge_step"] == 2

        _force_nudge_due(contact["id"])
        assert bot.process_due_nudges() == 1
        last = api.sent[-1]
        assert "некогда" in last["text"].lower()
        payloads = [btn.get("payload") for row in last["buttons"] for btn in row]
        assert "nudge:later" in payloads
        assert "stop_nudge" not in payloads
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["nudge_step"] == 3
        assert contact["next_nudge_at"]

        _force_nudge_due(contact["id"])
        assert bot.process_due_nudges() == 1
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["nudge_step"] == 4
        assert contact["next_nudge_at"]
    finally:
        _cleanup(max_user_id)


def test_nudge_skips_stopped():
    bot, api, max_user_id = _bot()
    try:
        _finish_gift(bot, max_user_id, occasion="occasion:just")
        contact = MessengerService().get_by_max(max_user_id)
        MessengerService().stop(contact)
        _force_nudge_due(contact["id"])
        api.sent.clear()
        assert bot.process_due_nudges() == 0
        assert api.sent == []
    finally:
        _cleanup(max_user_id)


def test_ready_followup_waits_if_on_site_then_sends():
    bot, api, max_user_id = _bot()
    try:
        _finish_gift(bot, max_user_id)
        svc = MessengerService()
        contact = svc.get_by_max(max_user_id)
        gen_id = str(uuid.uuid4())
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO generations (
                    id, created_at, status, user_id, purchased, title
                ) VALUES (?, '2026-09-11T10:00:00', 'success', ?, 0, 'Тест')
                """,
                (gen_id, contact["user_id"]),
            )
        svc.on_generation_ready(user_id=contact["user_id"], generation_id=gen_id)
        contact = svc.get_by_max(max_user_id)
        assert not contact["next_nudge_at"]
        svc.touch_site(contact["user_id"])
        with get_connection() as conn:
            conn.execute(
                "UPDATE messenger_followups SET due_at = ? WHERE generation_id = ?",
                ("2000-01-01T00:00:00+00:00", gen_id),
            )
        api.sent.clear()
        assert bot.process_due_followups() == 0
        assert api.sent == []
        with get_connection() as conn:
            conn.execute(
                "UPDATE messenger_contacts SET last_site_at = ? WHERE id = ?",
                ("2000-01-01T00:00:00+00:00", contact["id"]),
            )
            conn.execute(
                "UPDATE messenger_followups SET due_at = ? WHERE generation_id = ?",
                ("2000-01-01T00:00:00+00:00", gen_id),
            )
        assert bot.process_due_followups() == 1
        last = api.sent[-1]
        assert "готова" in last["text"].lower() or "уже готово" in last["text"].lower()
        labels = [btn.get("text") for row in last["buttons"] for btn in row]
        assert any("слушать" in l.lower() for l in labels)
        assert any("open=listen" in (btn.get("url") or "") for row in last["buttons"] for btn in row)
    finally:
        _cleanup(max_user_id)


def test_unpaid_followup_after_preview():
    bot, api, max_user_id = _bot()
    try:
        _finish_gift(bot, max_user_id, occasion="occasion:just")
        svc = MessengerService()
        contact = svc.get_by_max(max_user_id)
        gen_id = str(uuid.uuid4())
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO generations (
                    id, created_at, status, user_id, purchased, title
                ) VALUES (?, '2026-09-11T10:00:00', 'success', ?, 0, 'Тест')
                """,
                (gen_id, contact["user_id"]),
            )
        svc.on_generation_ready(user_id=contact["user_id"], generation_id=gen_id)
        svc.on_preview_played(user_id=contact["user_id"], generation_id=gen_id)
        with get_connection() as conn:
            conn.execute(
                "UPDATE messenger_contacts SET last_site_at = ? WHERE id = ?",
                ("2000-01-01T00:00:00+00:00", contact["id"]),
            )
            conn.execute(
                "UPDATE messenger_followups SET due_at = ? WHERE generation_id = ? AND kind = ?",
                ("2000-01-01T00:00:00+00:00", gen_id, "unpaid_expert"),
            )
        api.sent.clear()
        assert bot.process_due_followups() == 1
        last = api.sent[-1]
        assert "расширенном" in last["text"].lower()
        labels = [btn.get("text") for row in last["buttons"] for btn in row]
        assert any("расширенный режим" in l.lower() for l in labels)
        assert any("слушать" in l.lower() for l in labels)
        svc.on_generation_purchased(user_id=contact["user_id"], generation_id=gen_id)
        api.sent.clear()
        assert bot.process_due_followups() == 0
    finally:
        _cleanup(max_user_id)


def test_studio_open_keeps_next_evening():
    bot, api, max_user_id = _bot()
    try:
        _finish_gift(bot, max_user_id, occasion="occasion:holiday")
        svc = MessengerService()
        contact = svc.get_by_max(max_user_id)
        first = contact["next_nudge_at"]
        assert first
        contact = svc.note_studio_opened(contact)
        assert contact["next_nudge_at"]
        api.sent.clear()
        assert bot.process_due_nudges() == 0
    finally:
        _cleanup(max_user_id)


def test_evening_after_uses_local_hour():
    after = datetime(2026, 9, 15, 23, 0, tzinfo=timezone.utc)
    iso = evening_after("Europe/Moscow", days=1, after=after)
    sent = datetime.fromisoformat(iso)
    from backend.services.nudge_schedule import resolve_tz, SEND_HOUR

    local_hour = sent.astimezone(resolve_tz("Europe/Moscow")).hour
    assert local_hour == SEND_HOUR
    assert sent > after


def test_opened_studio_nudge_copy_and_snooze():
    bot, api, max_user_id = _bot()
    try:
        _finish_gift(bot, max_user_id)
        svc = MessengerService()
        contact = svc.get_by_max(max_user_id)
        svc.note_studio_opened(contact)
        with get_connection() as conn:
            conn.execute(
                "UPDATE messenger_contacts SET last_site_at = ?, brief_detail = ? WHERE id = ?",
                ("2026-09-15T10:00:00+00:00", "всегда оставляла свет на кухне", contact["id"]),
            )
        _force_nudge_due(contact["id"])
        api.sent.clear()
        assert bot.process_due_nudges() == 1
        assert "заглянул в студию" in api.sent[-1]["text"].lower() or "зашёл и вышел" in api.sent[-1]["text"].lower()
        _force_nudge_due(contact["id"])
        assert bot.process_due_nudges() == 1
        assert "свет на кухне" in api.sent[-1]["text"].lower()
        _force_nudge_due(contact["id"])
        assert bot.process_due_nudges() == 1
        _cb(bot, max_user_id, "nudge:later")
        assert "напомню позднее" in api.sent[-1]["text"].lower()
        contact = svc.get_by_max(max_user_id)
        assert contact["next_nudge_at"]
        assert contact["nudge_step"] >= 3
        api.sent.clear()
        assert bot.process_due_nudges() == 0
        assert api.sent == []
    finally:
        _cleanup(max_user_id)


def test_purchase_schedules_how_received():
    bot, api, max_user_id = _bot()
    try:
        _finish_gift(bot, max_user_id)
        svc = MessengerService()
        contact = svc.get_by_max(max_user_id)
        gen_id = str(uuid.uuid4())
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO generations (
                    id, created_at, status, user_id, purchased, title
                ) VALUES (?, '2026-09-11T10:00:00', 'success', ?, 1, 'Тест')
                """,
                (gen_id, contact["user_id"]),
            )
        svc.on_generation_purchased(user_id=contact["user_id"], generation_id=gen_id)
        contact = svc.get_by_max(max_user_id)
        assert not contact["next_nudge_at"]
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT kind FROM messenger_followups WHERE contact_id = ? AND canceled_at IS NULL",
                (contact["id"],),
            ).fetchall()
        kinds = {r["kind"] for r in rows}
        assert "how_received" in kinds
        with get_connection() as conn:
            conn.execute(
                "UPDATE messenger_followups SET due_at = ? WHERE contact_id = ? AND kind = ?",
                ("2000-01-01T00:00:00+00:00", contact["id"], "how_received"),
            )
        api.sent.clear()
        assert bot.process_due_followups() == 1
        assert "как впечатление" in api.sent[-1]["text"].lower() or "подарок" in api.sent[-1]["text"].lower()
        with get_connection() as conn:
            rows2 = conn.execute(
                "SELECT kind FROM messenger_followups WHERE contact_id = ? AND sent_at IS NULL AND canceled_at IS NULL",
                (contact["id"],),
            ).fetchall()
        kinds2 = {r["kind"] for r in rows2}
        assert "next_person" in kinds2
    finally:
        _cleanup(max_user_id)


def test_bot_started_resets_old_brief_and_sends_cover():
    bot, api, max_user_id = _bot()
    try:
        _cb(bot, max_user_id, "accept")
        _text(bot, max_user_id, "бабушке")
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["brief_whom"] == "бабушке"
        api.sent.clear()
        bot.handle_update(
            {
                "update_type": "bot_started",
                "chat_id": int(max_user_id),
                "user": {"user_id": int(max_user_id), "name": f"tmax_{max_user_id}"},
            }
        )
        contact = MessengerService().get_by_max(max_user_id)
        assert (contact.get("brief_whom") or "") == ""
        assert contact["funnel_stage"] == "gate"
        first = api.sent[0]["text"].lower()
        assert "спеть" in first or "говорится" in first
        assert "дате" not in first
        assert api.sent[0]["image_url"] or api.sent[0]["image_payload"]
    finally:
        _cleanup(max_user_id)


def test_price_question_does_not_become_whom():
    bot, api, max_user_id = _bot()
    try:
        _cb(bot, max_user_id, "accept")
        _text(bot, max_user_id, "сколько стоит?")
        contact = MessengerService().get_by_max(max_user_id)
        assert (contact.get("brief_whom") or "") == ""
        last = api.sent[-1]
        assert "черновик" in last["text"].lower() or "вариант" in last["text"].lower()
        payloads = [btn.get("payload") or "" for row in last["buttons"] for btn in row]
        assert "whom:mom" in payloads
    finally:
        _cleanup(max_user_id)


def test_voice_garbage_reasks():
    bot, api, max_user_id = _bot()
    try:
        _cb(bot, max_user_id, "accept")
        _cb(bot, max_user_id, "whom:mom")
        _cb(bot, max_user_id, "occasion:just")
        _cb(bot, max_user_id, "detail:skip")
        _cb(bot, max_user_id, "genre:pop")
        _cb(bot, max_user_id, "sound:uplifting")
        _text(bot, max_user_id, "синий трактор")
        contact = MessengerService().get_by_max(max_user_id)
        assert (contact.get("brief_voice") or "") == ""
        last = api.sent[-1]["text"].lower()
        assert "голос" in last
        payloads = [btn.get("payload") or "" for row in api.sent[-1]["buttons"] for btn in row]
        assert "voice:female" in payloads
    finally:
        _cleanup(max_user_id)


def test_legal_document_stays_in_chat():
    bot, api, max_user_id = _bot()
    try:
        bot.handle_update(
            {
                "update_type": "bot_started",
                "chat_id": int(max_user_id),
                "user": {"user_id": int(max_user_id), "name": f"tmax_{max_user_id}"},
            }
        )
        api.sent.clear()
        _cb(bot, max_user_id, "legal:privacy:1")
        last = api.sent[-1]
        assert "политик" in last["text"].lower() or "персональн" in last["text"].lower()
        urls = [btn.get("url") or "" for row in last["buttons"] for btn in row]
        assert not any(u.startswith("http") for u in urls)
        payloads = [btn.get("payload") or "" for row in last["buttons"] for btn in row]
        assert "accept" in payloads
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["funnel_stage"] == "gate"
        first_mid = last.get("mid") or "m1"
        api.sent.clear()
        _cb(bot, max_user_id, "legal:privacy:2")
        assert api.edited
        assert api.edited[-1]["mid"] == first_mid
        assert api.sent == []
        _cb(bot, max_user_id, "accept")
        assert first_mid in api.deleted
    finally:
        _cleanup(max_user_id)


def test_whom_and_occasion_new_grids():
    bot, api, max_user_id = _bot()
    try:
        _cb(bot, max_user_id, "accept")
        whom_msg = [m for m in api.sent if "кого" in m["text"].lower()][-1]
        rows = whom_msg["buttons"]
        payloads = [btn.get("payload") or "" for row in rows for btn in row]
        assert payloads == [
            "whom:husband",
            "whom:wife",
            "whom:boyfriend",
            "whom:girlfriend",
            "whom:buddy",
            "whom:pal",
            "whom:mom",
            "whom:dad",
            "whom:relative",
            "whom:child",
            "whom:write",
        ]
        labels = [btn.get("text") or "" for row in rows for btn in row]
        assert labels[-1].endswith("Напишу сам")
        assert (whom_msg.get("image_url") or "").endswith("max-whom.jpg") or whom_msg.get(
            "image_payload"
        )
        assert any("Маме" in (x or "") for x in labels)
        assert any("Ребёнку" in (x or "") for x in labels)
        assert any(x.startswith("👩") for x in labels)
        _cb(bot, max_user_id, "whom:wife")
        last = api.sent[-1]
        assert "поводу" in last["text"].lower() or "о чём" in last["text"].lower()
        occ = [btn.get("payload") or "" for row in last["buttons"] for btn in row]
        assert occ == [
            "occasion:birthday",
            "occasion:support",
            "occasion:wedding",
            "occasion:joke",
            "occasion:anniversary",
            "occasion:confession",
            "occasion:corporate",
            "occasion:just",
            "occasion:write",
        ]
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["brief_whom"] == "жене"
        api.sent.clear()
        _cb(bot, max_user_id, "occasion:wedding")
        last = api.sent[-1]["text"].lower()
        assert "лена" in last
        assert "кухн" in last
        assert "зовут" in last
        contact = MessengerService().get_by_max(max_user_id)
        assert "свадьб" in (contact.get("brief_mood") or "").lower()
    finally:
        _cleanup(max_user_id)


def test_detail_lands_in_studio_brief():
    bot, api, max_user_id = _bot()
    try:
        _cb(bot, max_user_id, "accept")
        _cb(bot, max_user_id, "whom:mom")
        _cb(bot, max_user_id, "occasion:birthday")
        _text(bot, max_user_id, "Елена, всегда оставляла свет на кухне")
        _cb(bot, max_user_id, "genre:pop")
        _cb(bot, max_user_id, "sound:peaceful")
        _cb(bot, max_user_id, "voice:female")
        contact = MessengerService().get_by_max(max_user_id)
        brief = (contact.get("brief") or "").lower()
        assert "свет на кухне" in brief
        assert "маме" in brief
        assert "женский" in brief
        assert "кому:" not in brief
        last = api.sent[-1]["text"].lower()
        assert "держу" not in last
        assert "сверим" in last
        assert "свет на кухне" in last
    finally:
        _cleanup(max_user_id)


def test_genre_and_mood_have_nine_choices():
    bot, api, max_user_id = _bot()
    try:
        _cb(bot, max_user_id, "accept")
        _cb(bot, max_user_id, "whom:mom")
        _cb(bot, max_user_id, "occasion:birthday")
        _cb(bot, max_user_id, "detail:skip")
        last = api.sent[-1]
        genres = [
            btn.get("payload") or ""
            for row in last["buttons"]
            for btn in row
            if (btn.get("payload") or "").startswith("genre:")
            and btn.get("payload") != "genre:write"
        ]
        assert len(genres) == 9
        assert all(len(row) <= 2 for row in last["buttons"])
        assert "genre:chanson" in genres
        assert "genre:jazz" in genres
        _cb(bot, max_user_id, "genre:chanson")
        last = api.sent[-1]
        moods = [
            btn.get("payload") or ""
            for row in last["buttons"]
            for btn in row
            if (btn.get("payload") or "").startswith("sound:")
            and btn.get("payload") != "sound:write"
        ]
        assert len(moods) == 9
        assert all(len(row) <= 2 for row in last["buttons"])
        assert "sound:joyful" in moods
        assert "sound:nostalgic" in moods
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["brief_genre"] == "Шансон"
    finally:
        _cleanup(max_user_id)


def test_edit_whom_keeps_rest_of_brief():
    bot, api, max_user_id = _bot()
    try:
        _cb(bot, max_user_id, "accept")
        _cb(bot, max_user_id, "whom:mom")
        _cb(bot, max_user_id, "occasion:birthday")
        _cb(bot, max_user_id, "detail:skip")
        _cb(bot, max_user_id, "genre:pop")
        _cb(bot, max_user_id, "sound:uplifting")
        _cb(bot, max_user_id, "voice:female")
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["funnel_stage"] == "confirm"
        assert contact["brief_whom"] == "маме"
        assert "день рождения" in (contact.get("brief_mood") or "").lower()
        assert contact["brief_genre"] == "Поп"
        _cb(bot, max_user_id, "confirm:edit")
        _cb(bot, max_user_id, "edit:whom")
        api.sent.clear()
        _cb(bot, max_user_id, "whom:wife")
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["brief_whom"] == "жене"
        assert "день рождения" in (contact.get("brief_mood") or "").lower()
        assert contact["brief_genre"] == "Поп"
        assert contact["funnel_stage"] == "confirm"
        last = api.sent[-1]["text"].lower()
        assert "сверим" in last
        assert "жене" in last
        assert "повод" not in last or "день рождения" in last
    finally:
        _cleanup(max_user_id)


def test_nudge_branch1_mid_survey_stuck_and_resume():
    bot, api, max_user_id = _bot()
    try:
        _cb(bot, max_user_id, "accept")
        _cb(bot, max_user_id, "whom:mom")
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["funnel_stage"] == "occasion"
        assert contact["next_nudge_at"]

        _force_nudge_due(contact["id"])
        api.sent.clear()
        assert bot.process_due_nudges() == 1
        last = api.sent[-1]
        assert "черновик песни ждёт продолжения" in last["text"].lower()
        payloads = [btn.get("payload") for row in last["buttons"] for btn in row]
        assert "nudge:resume_survey" in payloads
        assert "nudge:start_over" in payloads

        api.sent.clear()
        _cb(bot, max_user_id, "nudge:resume_survey")
        assert len(api.sent) == 1
        assert "повод" in api.sent[-1]["text"].lower()

        api.sent.clear()
        _cb(bot, max_user_id, "nudge:start_over")
        assert len(api.sent) == 1
        assert "кого" in api.sent[-1]["text"].lower() or "кому" in api.sent[-1]["text"].lower()
    finally:
        _cleanup(max_user_id)


def test_nudge_branch3_opened_site_no_generation():
    bot, api, max_user_id = _bot()
    try:
        _finish_gift(bot, max_user_id, whom="whom:mom")
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["funnel_stage"] == "sent_to_site"
        MessengerService().touch_site(contact["user_id"])
        contact = MessengerService().get_by_max(max_user_id)
        assert contact["last_site_at"]

        _force_nudge_due(contact["id"])
        api.sent.clear()
        assert bot.process_due_nudges() == 1
        last = api.sent[-1]
        assert "заглянул в студию" in last["text"].lower()
        assert "маме" in last["text"].lower()
        btn_labels = [btn.get("text") for row in last["buttons"] for btn in row]
        assert any("перейти к созданию" in b.lower() for b in btn_labels)
    finally:
        _cleanup(max_user_id)


def test_followup_periodic_retention_branch6():
    bot, api, max_user_id = _bot()
    try:
        _finish_gift(bot, max_user_id)
        contact = MessengerService().get_by_max(max_user_id)
        svc = MessengerService()
        gen_id = str(uuid.uuid4())
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO generations (
                    id, created_at, status, user_id, purchased, title
                ) VALUES (?, '2026-09-11T10:00:00', 'success', ?, 1, 'Тест')
                """,
                (gen_id, contact["user_id"]),
            )
        svc.on_generation_purchased(user_id=contact["user_id"], generation_id=gen_id)

        with get_connection() as conn:
            conn.execute(
                "UPDATE messenger_followups SET due_at = ? WHERE contact_id = ? AND kind = ?",
                ("2000-01-01T00:00:00+00:00", contact["id"], "how_received"),
            )
        assert bot.process_due_followups() == 1

        with get_connection() as conn:
            conn.execute(
                "UPDATE messenger_followups SET due_at = ? WHERE contact_id = ? AND kind = ?",
                ("2000-01-01T00:00:00+00:00", contact["id"], "next_person"),
            )
        api.sent.clear()
        assert bot.process_due_followups() == 1
        assert "праздник" in api.sent[-1]["text"].lower() or "повод" in api.sent[-1]["text"].lower()

        with get_connection() as conn:
            conn.execute(
                "UPDATE messenger_followups SET due_at = ? WHERE contact_id = ? AND kind = ?",
                ("2000-01-01T00:00:00+00:00", contact["id"], "next_person_periodic"),
            )
        api.sent.clear()
        assert bot.process_due_followups() == 1
        assert "музыка" in api.sent[-1]["text"].lower() or "кому подарим" in api.sent[-1]["text"].lower()
    finally:
        _cleanup(max_user_id)
