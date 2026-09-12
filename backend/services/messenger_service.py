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
STAGE_OCCASION = "occasion"
STAGE_MOOD = "mood"
STAGE_THEME = "theme"
STAGE_ABOUT = "about"
STAGE_DETAIL = "detail"
STAGE_UNSAID = "unsaid"
STAGE_GENRE = "genre"
STAGE_SOUND = "sound"
STAGE_VOICE = "voice"
STAGE_CONFIRM = "confirm"
STAGE_BIZ_GOAL = "biz_goal"
STAGE_BIZ_DETAIL = "biz_detail"
STAGE_BIZ_TONE = "biz_tone"
STAGE_SENT = "sent_to_site"
STAGE_STOPPED = "stopped"

WHOM_LABELS = {
    "mom": "маме",
    "dad": "папе",
    "partner": "половинке",
    "buddy": "другу",
    "pal": "подруге",
    "her": "половинке",
    "him": "половинке",
    "friend": "другу",
}
OCCASION_LABELS = {
    "birthday": "день рождения",
    "anniversary": "годовщина",
    "just": "просто так, без повода",
    "holiday": "скоро праздник",
    "unsaid": "не могу сказать вслух",
}
MOOD_LABELS = OCCASION_LABELS
THEME_LABELS = {
    "love": "про любовь",
    "story": "про случай из жизни",
    "feeling": "про чувство или настроение",
    "chapter": "новая глава",
    "release": "отпустить и выдохнуть",
    "high": "кайф от момента",
    "nostalgia": "ностальгия",
    "dunno": "пока не знаю",
}
GENRE_LABELS = {
    "pop": "Поп",
    "rock": "Рок",
    "rap": "Реп",
    "electronic": "Электронная",
    "lofi": "Ло-фай",
    "ballad": "Баллада",
}
SOUND_LABELS = {
    "uplifting": "энергично",
    "romantic": "романтично",
    "peaceful": "спокойно",
    "melancholy": "меланхолично",
    "adventurous": "эпично",
    "party": "вечеринка",
    "warm": "спокойно",
    "soft": "романтично",
    "drive": "энергично",
    "smile": "радостно",
    "anthem": "эпично",
}
VOICE_LABELS = {
    "female": "женский",
    "male": "мужской",
    "duet": "дуэт",
    "auto": "на усмотрение",
}
BIZ_GOAL_LABELS = {
    "ads": "реклама / бренд",
    "event": "корпоратив, праздник компании",
    "video": "саундтрек к видео",
    "jingle": "реклама / бренд",
    "client": "корпоратив, праздник компании",
}
BIZ_TONE_LABELS = {
    "energy": "энергично",
    "solid": "солидно",
    "friendly": "дружелюбно",
    "atmosphere": "атмосферно",
    "serious": "солидно",
    "light": "дружелюбно",
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


def compose_brief_business(goal: str, tone: str, detail: str = "") -> str:
    lines = []
    if goal:
        lines.append(f"Тип: бизнес — {goal}")
    else:
        lines.append("Тип: бизнес")
    if detail:
        lines.append(f"Деталь: {detail}")
    if tone:
        lines.append(f"Тон: {tone}")
    lines.append("Голос: на усмотрение продюсера")
    lines.append("Заметка: рекламный формат, не личный подарок")
    return "\n".join(lines)


def _iso_after(*, hours: int = 0, days: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours, days=days)).isoformat()


def _cap(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    return text[0].upper() + text[1:]


_EMPTY_ABOUT = {
    "пока не знаю",
    "пока не знаю, но хочу свою песню",
    "не указан",
    "не указан (для себя)",
    "конкретно никому",
}


def compose_brief(
    whom: str,
    mood: str,
    detail: str = "",
    sound: str = "",
    voice: str = "",
    plot: str = "gift",
    genre: str = "",
) -> str:
    whom = (whom or "").strip()
    mood = (mood or "").strip()
    if mood.lower() in _EMPTY_ABOUT:
        mood = ""
    detail = (detail or "").strip()
    sound = (sound or "").strip()
    voice = (voice or "").strip()
    genre = (genre or "").strip()
    plot = (plot or "gift").strip() or "gift"
    just = plot == "just" or whom.lower() in {"себе", "мне", "для себя"}
    parts: list[str] = []
    if just:
        if mood:
            parts.append(f"Песня про {mood}.")
        elif detail:
            parts.append("Песня без адресата.")
        else:
            parts.append("Песня без конкретного адресата.")
    else:
        head = "Песня"
        if whom:
            head += f" {whom}"
        if mood:
            head += f", {mood}"
        parts.append(head + ".")
    if detail:
        parts.append(detail if detail.endswith((".", "!", "?")) else detail + ".")
    if genre:
        parts.append(f"Жанр {genre}.")
    if sound:
        parts.append(f"Настроение: {sound}.")
    if voice == "дуэт":
        parts.append("Дуэт, мужской и женский голос.")
    elif voice in {"женский", "мужской"}:
        parts.append(f"{_cap(voice)} голос.")
    if just:
        parts.append("Цельная песня по теме, не открытка.")
    elif "не могу сказать" in (mood or "").lower():
        parts.append("Мягко: то, что не выговаривается вслух. Без пафоса.")
    elif whom or mood or detail:
        parts.append("Чтобы адресат узнал себя с первой строки. Без канцелярита.")
    return " ".join(parts).strip()


class MessengerService:
    def __init__(self) -> None:
        init_db()

    def get_by_id(self, contact_id: str) -> dict | None:
        if not contact_id:
            return None
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM messenger_contacts WHERE id = ?",
                (contact_id,),
            ).fetchone()
        return dict(row) if row else None

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

    def get_max_contact_for_user(self, user_id: str) -> dict | None:
        if not user_id:
            return None
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM messenger_contacts
                WHERE user_id = ?
                  AND max_user_id IS NOT NULL
                  AND TRIM(max_user_id) != ''
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def touch_site(self, user_id: str) -> None:
        if not user_id:
            return
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET last_site_at = ?, updated_at = ?
                WHERE user_id = ?
                  AND max_user_id IS NOT NULL
                  AND TRIM(max_user_id) != ''
                """,
                (now, now, user_id),
            )

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
                    brief_detail, brief_sound, brief_voice,
                    last_channel, max_chat_id, messages_ok,
                    stopped_at, blocked_at, created_at, updated_at
                ) VALUES (?, NULL, ?, NULL, NULL, ?, '', '', '', '', '', '', 'max', ?, 0, NULL, NULL, ?, ?)
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
        if segment == "business":
            next_stage = STAGE_BIZ_GOAL
        elif segment == "just":
            next_stage = STAGE_THEME
        else:
            segment = "gift"
            next_stage = STAGE_TALK
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET segment = ?, funnel_stage = ?, funnel_await = '',
                    last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (segment, next_stage, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_stage(self, contact: dict, stage: str) -> dict:
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET funnel_stage = ?, funnel_await = '', last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (stage, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_await(self, contact: dict, kind: str) -> dict:
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET funnel_await = ?, last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (kind or "", now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_biz_goal(self, contact: dict, goal: str) -> dict:
        brief = compose_brief_business(
            goal, contact.get("brief_mood") or "", contact.get("brief_detail") or ""
        )
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET brief_whom = ?, brief = ?, funnel_stage = ?, funnel_await = '',
                    segment = 'business', last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (goal, brief, STAGE_BIZ_DETAIL, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_biz_detail(self, contact: dict, detail: str) -> dict:
        goal = contact.get("brief_whom") or ""
        brief = compose_brief_business(goal, contact.get("brief_mood") or "", detail)
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET brief_detail = ?, brief = ?, funnel_stage = ?, funnel_await = '',
                    last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (detail, brief, STAGE_BIZ_TONE, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_biz_tone(self, contact: dict, tone: str) -> dict:
        goal = contact.get("brief_whom") or ""
        brief = compose_brief_business(goal, tone, contact.get("brief_detail") or "")
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET brief_mood = ?, brief = ?, funnel_stage = ?, funnel_await = '',
                    last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (tone, brief, STAGE_VOICE, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def _gift_brief(self, contact: dict, **overrides: str) -> str:
        whom = overrides.get("brief_whom", contact.get("brief_whom") or "")
        mood = overrides.get("brief_mood", contact.get("brief_mood") or "")
        detail = overrides.get("brief_detail", contact.get("brief_detail") or "")
        sound = overrides.get("brief_sound", contact.get("brief_sound") or "")
        voice = overrides.get("brief_voice", contact.get("brief_voice") or "")
        genre = overrides.get("brief_genre", contact.get("brief_genre") or "")
        plot = overrides.get("segment", contact.get("segment") or "gift")
        return compose_brief(
            whom,
            mood,
            detail=detail,
            sound=sound,
            voice=voice,
            plot=plot,
            genre=genre,
        )

    def reset_song(self, contact: dict) -> dict:
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET funnel_stage = ?, brief = '', brief_whom = '', brief_mood = '',
                    brief_detail = '', brief_sound = '', brief_voice = '',
                    brief_genre = '', occasion_key = '', segment = '', funnel_await = '',
                    nudge_step = 0, next_nudge_at = NULL,
                    last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (STAGE_GATE, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_whom(self, contact: dict, whom: str, *, detail: str = "", plot: str = "gift") -> dict:
        extra = (detail or "").strip() or (contact.get("brief_detail") or "")
        plot = "just" if plot == "just" else "gift"
        stage = STAGE_ABOUT if plot == "just" else STAGE_OCCASION
        brief = self._gift_brief(
            contact, brief_whom=whom, brief_detail=extra, segment=plot
        )
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET brief_whom = ?, brief_detail = ?, brief = ?, funnel_stage = ?,
                    segment = ?, funnel_await = '', last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (whom, extra, brief, stage, plot, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_occasion(self, contact: dict, mood: str, *, occasion_key: str = "") -> dict:
        next_stage = STAGE_UNSAID if occasion_key == "unsaid" else STAGE_DETAIL
        brief = self._gift_brief(contact, brief_mood=mood)
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET brief_mood = ?, occasion_key = ?, brief = ?, funnel_stage = ?,
                    funnel_await = '', last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (mood, occasion_key, brief, next_stage, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_theme(self, contact: dict, theme: str, *, theme_key: str = "") -> dict:
        brief = self._gift_brief(contact, brief_mood=theme, segment="just")
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET brief_mood = ?, occasion_key = ?, brief = ?, funnel_stage = ?,
                    segment = 'just', funnel_await = '', last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (theme, theme_key, brief, STAGE_DETAIL, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_about(self, contact: dict, about: str) -> dict:
        return self.set_theme(contact, about, theme_key="")

    def set_genre(self, contact: dict, genre: str) -> dict:
        brief = self._gift_brief(contact, brief_genre=genre)
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET brief_genre = ?, brief = ?, funnel_stage = ?,
                    funnel_await = '', last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (genre, brief, STAGE_SOUND, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_mood(self, contact: dict, mood: str, *, occasion_key: str = "") -> dict:
        return self.set_occasion(contact, mood, occasion_key=occasion_key)

    def set_detail(self, contact: dict, detail: str) -> dict:
        brief = self._gift_brief(contact, brief_detail=detail)
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET brief_detail = ?, brief = ?, funnel_stage = ?,
                    funnel_await = '', last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (detail, brief, STAGE_GENRE, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_sound(self, contact: dict, sound: str) -> dict:
        brief = self._gift_brief(contact, brief_sound=sound)
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET brief_sound = ?, brief = ?, funnel_stage = ?,
                    funnel_await = '', last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (sound, brief, STAGE_VOICE, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def set_voice(self, contact: dict, voice: str) -> dict:
        brief = self._gift_brief(contact, brief_voice=voice)
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET brief_voice = ?, brief = ?, funnel_stage = ?,
                    funnel_await = '', last_channel = 'max', updated_at = ?
                WHERE id = ?
                """,
                (voice, brief, STAGE_CONFIRM, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def mark_sent_to_site(self, contact: dict) -> dict:
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET funnel_stage = ?, last_channel = 'max', updated_at = ?,
                    nudge_step = 0, next_nudge_at = ?
                WHERE id = ?
                """,
                (STAGE_SENT, now, _iso_after(hours=2), contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def note_studio_opened(self, contact: dict) -> dict:
        """Открыл студию по ссылке — 2-часовой пинг не нужен, сутки оставляем."""
        if int(contact.get("nudge_step") or 0) != 0:
            return contact
        if not (contact.get("next_nudge_at") or "").strip():
            return contact
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET next_nudge_at = ?, updated_at = ?
                WHERE id = ? AND nudge_step = 0 AND next_nudge_at IS NOT NULL
                """,
                (_iso_after(hours=24), now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def list_due_nudges(self, *, limit: int = 20) -> list[dict]:
        now = utc_now()
        limit = max(1, min(int(limit), 50))
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM messenger_contacts
                WHERE next_nudge_at IS NOT NULL
                  AND TRIM(next_nudge_at) != ''
                  AND next_nudge_at <= ?
                  AND messages_ok = 1
                  AND blocked_at IS NULL
                  AND funnel_stage = ?
                  AND COALESCE(nudge_step, 0) < 3
                ORDER BY next_nudge_at ASC
                LIMIT {limit}
                """,
                (now, STAGE_SENT),
            ).fetchall()
        return [dict(row) for row in rows]

    def advance_nudge(self, contact: dict) -> dict:
        step = int(contact.get("nudge_step") or 0)
        now = utc_now()
        if step <= 0:
            next_at = _iso_after(hours=24)
            new_step = 1
        elif step == 1:
            next_at = _iso_after(days=4)
            new_step = 2
        else:
            next_at = None
            new_step = 3
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET nudge_step = ?, next_nudge_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_step, next_at, now, contact["id"]),
            )
        return self.get_by_max(contact["max_user_id"]) or contact

    def delay_nudge(self, contact: dict, *, minutes: int = 15) -> None:
        later = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET next_nudge_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (later, utc_now(), contact["id"]),
            )

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

    def studio_url(self, contact: dict, *, open_to: str = "", next_path: str = "") -> str:
        from urllib.parse import quote

        token = self.make_login_token(contact["id"])
        base = (SITE_URL or "https://sozdaipesnu.ru").rstrip("/")
        url = f"{base}/api/auth/max?m={token}"
        if open_to in {"listen", "expert"}:
            url += f"&open={open_to}"
        allowed = {"/legal/terms", "/legal/privacy", "/legal/offer", "/"}
        path = (next_path or "").strip()
        if path in allowed:
            url += f"&next={quote(path)}"
        return url

    def silence_studio_nudges(self, contact: dict) -> None:
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_contacts
                SET next_nudge_at = NULL, nudge_step = 9, updated_at = ?
                WHERE id = ?
                """,
                (now, contact["id"]),
            )

    def _cancel_followups(
        self,
        *,
        contact_id: str | None = None,
        generation_id: str | None = None,
        kind: str | None = None,
    ) -> None:
        now = utc_now()
        clauses = ["canceled_at IS NULL", "sent_at IS NULL"]
        params: list = []
        if contact_id:
            clauses.append("contact_id = ?")
            params.append(contact_id)
        if generation_id:
            clauses.append("generation_id = ?")
            params.append(generation_id)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if len(params) < 1:
            return
        with get_connection() as conn:
            conn.execute(
                f"UPDATE messenger_followups SET canceled_at = ? WHERE {' AND '.join(clauses)}",
                [now, *params],
            )

    def schedule_followup(
        self,
        *,
        contact: dict,
        kind: str,
        generation_id: str,
        hours: int = 0,
        minutes: int = 0,
        days: int = 0,
    ) -> None:
        self._cancel_followups(
            contact_id=contact["id"],
            generation_id=generation_id,
            kind=kind,
        )
        now = utc_now()
        due = (
            datetime.now(timezone.utc)
            + timedelta(days=days, hours=hours, minutes=minutes)
        ).isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO messenger_followups (
                    id, contact_id, user_id, generation_id, kind,
                    due_at, sent_at, canceled_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?)
                """,
                (
                    str(uuid.uuid4()),
                    contact["id"],
                    contact.get("user_id") or "",
                    generation_id,
                    kind,
                    due,
                    now,
                ),
            )

    def on_generation_ready(self, *, user_id: str, generation_id: str) -> None:
        contact = self.get_max_contact_for_user(user_id)
        if not contact or not self.can_message(contact):
            return
        self.silence_studio_nudges(contact)
        state = self.generation_followup_state(generation_id)
        if int(state.get("purchased") or 0):
            return
        self.schedule_followup(
            contact=contact,
            kind="ready_listen",
            generation_id=generation_id,
            minutes=5,
        )

    def on_preview_played(self, *, user_id: str, generation_id: str) -> None:
        if not user_id or not generation_id:
            return
        now = utc_now()
        purchased = 0
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE generations
                SET previewed_at = COALESCE(previewed_at, ?)
                WHERE id = ?
                """,
                (now, generation_id),
            )
            row = conn.execute(
                "SELECT purchased FROM generations WHERE id = ?",
                (generation_id,),
            ).fetchone()
            purchased = int(row["purchased"] or 0) if row else 0
        self.touch_site(user_id)
        contact = self.get_max_contact_for_user(user_id)
        if not contact or not self.can_message(contact):
            return
        self._cancel_followups(
            contact_id=contact["id"],
            generation_id=generation_id,
            kind="ready_listen",
        )
        if purchased:
            self._cancel_followups(
                contact_id=contact["id"],
                generation_id=generation_id,
                kind="unpaid_preview",
            )
            return
        self.schedule_followup(
            contact=contact,
            kind="unpaid_preview",
            generation_id=generation_id,
            days=1,
        )

    def on_generation_purchased(self, *, user_id: str, generation_id: str) -> None:
        contact = self.get_max_contact_for_user(user_id)
        if not contact:
            return
        self._cancel_followups(contact_id=contact["id"], generation_id=generation_id)

    def list_due_followups(self, *, limit: int = 20) -> list[dict]:
        now = utc_now()
        limit = max(1, min(int(limit), 50))
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM messenger_followups
                WHERE sent_at IS NULL
                  AND canceled_at IS NULL
                  AND due_at <= ?
                ORDER BY due_at ASC
                LIMIT {limit}
                """,
                (now,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_followup_sent(self, followup_id: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE messenger_followups SET sent_at = ? WHERE id = ?",
                (utc_now(), followup_id),
            )

    def delay_followup(self, followup_id: str, *, minutes: int) -> None:
        later = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
        with get_connection() as conn:
            conn.execute(
                "UPDATE messenger_followups SET due_at = ? WHERE id = ? AND sent_at IS NULL",
                (later, followup_id),
            )

    def cancel_followup(self, followup_id: str) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE messenger_followups
                SET canceled_at = ?
                WHERE id = ? AND sent_at IS NULL
                """,
                (utc_now(), followup_id),
            )

    def generation_followup_state(self, generation_id: str) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, user_id, purchased, previewed_at, status, title
                FROM generations WHERE id = ?
                """,
                (generation_id,),
            ).fetchone()
        if not row:
            return {}
        return dict(row)

    def site_is_recent(self, contact: dict, *, minutes: int = 3) -> bool:
        raw = (contact.get("last_site_at") or "").strip()
        if not raw:
            return False
        try:
            seen = datetime.fromisoformat(raw)
        except ValueError:
            return False
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - seen.astimezone(timezone.utc)
        return delta.total_seconds() <= minutes * 60
