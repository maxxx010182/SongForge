"""Карточка контакта мессенджеров: согласия, brief, вход на сайт."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

from datetime import datetime, timedelta, timezone

from backend.database.db import get_connection, init_db, utc_now
from backend.settings import MAX_BOT_TOKEN, MAX_WEBHOOK_SECRET, SITE_URL

LEGAL_DOC_VERSION = "2026-07"
LOGIN_TTL_SEC = 7 * 24 * 3600
STAGE_GATE = "gate"
STAGE_SEGMENT = "segment"
STAGE_TALK = "talk"
STAGE_MOOD = "mood"
STAGE_BIZ_GOAL = "biz_goal"
STAGE_BIZ_TONE = "biz_tone"
STAGE_SENT = "sent_to_site"
STAGE_STOPPED = "stopped"

WHOM_LABELS = {
    "mom": "маме",
    "her": "любимой",
    "him": "любимому",
    "friend": "другу",
    "self": "себе",
}
OCCASION_LABELS = {
    "birthday": "день рождения",
    "just": "просто так",
    "holiday": "скоро праздник",
}
MOOD_LABELS = OCCASION_LABELS
BIZ_GOAL_LABELS = {
    "ads": "реклама и контент",
    "jingle": "джингл бренда",
    "client": "подарок клиенту",
    "event": "корпоратив",
}
BIZ_TONE_LABELS = {
    "serious": "серьёзно и статусно",
    "light": "легко, с юмором",
}


def webhook_secret() -> str:
    if MAX_WEBHOOK_SECRET:
        return MAX_WEBHOOK_SECRET.strip()
    token = (MAX_BOT_TOKEN or "").strip()
    if not token:
        return ""
    digest = hmac.new(b"sf-max-wh", token.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:32]


def _link_secret() -> bytes:
    raw = (MAX_WEBHOOK_SECRET or MAX_BOT_TOKEN or "dev").strip()
    return hmac.new(b"sf-max-link", raw.encode("utf-8"), hashlib.sha256).digest()


def compose_brief_business(goal: str, tone: str) -> str:
    goal = (goal or "").strip()
    tone = (tone or "").strip()
    if goal and tone:
        return f"Для бизнеса: {goal}. {tone[0].upper() + tone[1:]}."
    if goal:
        return f"Для бизнеса: {goal}."
    return tone


def compose_brief(whom: str, mood: str) -> str:
    whom = (whom or "").strip()
    mood = (mood or "").strip()
    if mood:
        mood_cap = mood[0].upper() + mood[1:]
    else:
        mood_cap = ""
    if whom and mood_cap:
        return f"Песня {whom}. {mood_cap}."
    if whom:
        return f"Песня {whom}."
    return mood_cap


class MessengerService:
    def __init__(self) -> None:
        init_db()

    def get_by_max(self, max_user_id: str | int) -> dict | None:
        max_user_id = str(max_user_id).strip()
        if not max_user_id:
            return None
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM messenger_contacts WHERE max_user_id = ?",
                (max_user_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_brief_for_user(self, user_id: str) -> str:
        if not user_id:
            return ""
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT brief FROM messenger_contacts
                WHERE user_id = ? AND TRIM(brief) != ''
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return (row["brief"] or "").strip() if row else ""

    def get_or_create_by_max(
        self,
        *,
        max_user_id: str | int,
        chat_id: str | int | None = None,
        name: str = "",
    ) -> dict:
        max_user_id = str(max_user_id).strip()
        existing = self.get_by_max(max_user_id)
        now = utc_now()
        chat = str(chat_id).strip() if chat_id is not None else ""
        if existing:
            if chat and existing.get("max_chat_id") != chat:
                with get_connection() as conn:
                    conn.execute(
                        """
                        UPDATE messenger_contacts
                        SET max_chat_id = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (chat, now, existing["id"]),
                    )
                existing["max_chat_id"] = chat
                existing["updated_at"] = now
            return existing

        contact_id = str(uuid.uuid4())
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO messenger_contacts (
                    id, user_id, max_user_id, vk_user_id, tg_user_id,
                    funnel_stage, brief, brief_whom, brief_mood,
                    last_channel, max_chat_id, messages_ok,
                    stopped_at, blocked_at, created_at, updated_at
                ) VALUES (?, NULL, ?, NULL, NULL, ?, '', '', '', 'max', ?, 0, NULL, NULL, ?, ?)
                """,
                (contact_id, max_user_id, STAGE_GATE, chat or None, now, now),
            )
        contact = self.get_by_max(max_user_id)
        if not contact:
            raise RuntimeError("Не удалось создать карточку MAX")
        return contact

    def _add_consent(
        self,
        conn,
        *,
        contact_id: str,
        kind: str,
        channel: str = "max",
        details: dict | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO messenger_consents (
                id, contact_id, channel, kind, doc_version, created_at, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                contact_id,
                channel,
                kind,
                LEGAL_DOC_VERSION,
                utc_now(),
                json.dumps(details or {}, ensure_ascii=False),
            ),
        )

    def accept(
        self,
        contact: dict,
        *,
        user_id: str,
        name: str = "",
    ) -> dict:
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET user_id = ?, funnel_stage = ?, segment = CASE
                        WHEN TRIM(COALESCE(segment, '')) = '' THEN 'gift'
                        ELSE segment
                    END,
                    messages_ok = 1,
                    stopped_at = NULL, blocked_at = NULL,
                    last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (user_id, STAGE_TALK, now, contact["id"]),
            )
            self._add_consent(
                conn,
                contact_id=contact["id"],
                kind="legal",
                details={"name": name},
            )
            self._add_consent(
                conn,
                contact_id=contact["id"],
                kind="messages",
                details={"name": name},
            )
        updated = self.get_by_max(contact["max_user_id"])
        return updated or contact

    def resume_messages(self, contact: dict) -> dict:
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET messages_ok = 1, stopped_at = NULL, blocked_at = NULL,
                    funnel_stage = CASE
                        WHEN funnel_stage = ? THEN ?
                        ELSE funnel_stage
                    END,
                    last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (STAGE_STOPPED, STAGE_TALK, now, contact["id"]),
            )
            self._add_consent(conn, contact_id=contact["id"], kind="messages")
        return self.get_by_max(contact["max_user_id"]) or contact

    def stop(self, contact: dict) -> dict:
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET messages_ok = 0, stopped_at = ?, funnel_stage = ?,
                    next_nudge_at = NULL,
                    last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (now, STAGE_STOPPED, now, contact["id"]),
            )
            self._add_consent(conn, contact_id=contact["id"], kind="stop")
        return self.get_by_max(contact["max_user_id"]) or contact

    def mark_blocked(self, contact: dict) -> None:
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET messages_ok = 0, blocked_at = ?, stopped_at = COALESCE(stopped_at, ?),
                    last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (now, now, now, contact["id"]),
            )

    def set_segment(self, contact: dict, segment: str) -> dict:
        segment = "business" if segment == "business" else "gift"
        next_stage = STAGE_BIZ_GOAL if segment == "business" else STAGE_TALK
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET segment = ?, funnel_stage = ?, last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (segment, next_stage, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_biz_goal(self, contact: dict, goal: str) -> dict:
        brief = compose_brief_business(goal, contact.get("brief_mood") or "")
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET brief_whom = ?, brief = ?, funnel_stage = ?,
                    last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (goal, brief, STAGE_BIZ_TONE, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_biz_tone(self, contact: dict, tone: str) -> dict:
        goal = contact.get("brief_whom") or ""
        brief = compose_brief_business(goal, tone)
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET brief_mood = ?, brief = ?, funnel_stage = ?,
                    last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (tone, brief, STAGE_SENT, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_whom(self, contact: dict, whom: str) -> dict:
        brief = compose_brief(whom, contact.get("brief_mood") or "")
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET brief_whom = ?, brief = ?, funnel_stage = ?,
                    last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (whom, brief, STAGE_MOOD, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_mood(self, contact: dict, mood: str, *, occasion_key: str = "") -> dict:
        whom = contact.get("brief_whom") or ""
        brief = compose_brief(whom, mood)
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET brief_mood = ?, occasion_key = ?, brief = ?, funnel_stage = ?,
                    last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (mood, occasion_key, brief, STAGE_SENT, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def mark_sent_to_site(self, contact: dict) -> dict:
        now = utc_now()
        nudge_at = (
            datetime.now(timezone.utc) + timedelta(hours=2)
        ).isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET funnel_stage = ?, last_channel = 'max', updated_at = ?,
                    nudge_step = 0, next_nudge_at = ?
                WHERE id = ?
                """,
                (STAGE_SENT, now, nudge_at, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def has_legal(self, contact: dict) -> bool:
        if contact.get("user_id"):
            return True
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM messenger_consents
                WHERE contact_id = ? AND kind = 'legal'
                LIMIT 1
                """,
                (contact["id"],),
            ).fetchone()
        return bool(row)

    def can_message(self, contact: dict) -> bool:
        if contact.get("blocked_at"):
            return False
        if contact.get("stopped_at") and not contact.get("messages_ok"):
            return False
        return bool(contact.get("messages_ok"))

    def make_login_token(self, contact_id: str, ttl_sec: int = LOGIN_TTL_SEC) -> str:
        exp = int(time.time()) + ttl_sec
        payload = f"{contact_id}.{exp}"
        sig = hmac.new(_link_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:20]
        return f"{payload}.{sig}"

    def verify_login_token(self, token: str) -> dict | None:
        token = (token or "").strip()
        parts = token.split(".")
        if len(parts) != 3:
            return None
        contact_id, exp_s, sig = parts
        try:
            exp = int(exp_s)
        except ValueError:
            return None
        if exp < int(time.time()):
            return None
        payload = f"{contact_id}.{exp_s}"
        expected = hmac.new(
            _link_secret(), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:20]
        if not hmac.compare_digest(sig, expected):
            return None
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM messenger_contacts WHERE id = ?",
                (contact_id,),
            ).fetchone()
        if not row or not row["user_id"]:
            return None
        return dict(row)

    def studio_url(self, contact: dict) -> str:
        token = self.make_login_token(contact["id"])
        base = (SITE_URL or "https://sozdaipesnu.ru").rstrip("/")
        return f"{base}/api/auth/max?m={token}"
