"""Воронка MAX по сценарию копирайтера: 3 сюжета, до 6 шагов, бизнес сбоку."""

from __future__ import annotations

from backend.logger import log
from backend.services.auth_service import AuthService
from backend.services.max_api import MaxApi
from backend.services.max_legal import legal_page
from backend.services.max_funnel import (
    ABOUT_TEXT,
    ABOUT_WAIT,
    BIZ_DETAIL_TEXT,
    BIZ_GOAL_TEXT,
    BIZ_SWITCH_TEXT,
    BIZ_TONE_TEXT,
    CONFIRM_FOOTER,
    DETAIL_JUST,
    DETAIL_WAIT,
    FAQ_TEXT,
    GATE_FORMAT,
    GATE_RETURN_TEXT,
    GATE_TEXT,
    GENRE_TEXT,
    GENRE_WAIT,
    GREET_STAY_TEXT,
    LATER_TEXT,
    OCCASION_TEXT,
    RESUME_TEXT,
    SOUND_TEXT,
    STOP_TEXT,
    STUDIO_CTA,
    STUDIO_FORMAT,
    studio_legal_html,
    THEME_TEXT,
    UNSAID_TEXT,
    UNSAID_WAIT,
    VOICE_RETRY_TEXT,
    VOICE_TEXT,
    WHOM_RETRY,
    WHOM_TEXT,
    WHOM_WRITE_PROMPT,
    biz_studio_mirror,
    detail_gift_text,
    human_recap,
    is_just_plot,
    is_price_question,
    is_skip,
    looks_business,
    occasion_key_of,
    parse_detail,
    parse_genre,
    parse_occasion,
    parse_sound,
    parse_theme,
    parse_voice,
    parse_whom,
    studio_mirror,
    theme_key_of,
)
from backend.services.messenger_service import (
    BIZ_GOAL_LABELS,
    BIZ_TONE_LABELS,
    OCCASION_LABELS,
    STAGE_ABOUT,
    STAGE_BIZ_DETAIL,
    STAGE_BIZ_GOAL,
    STAGE_BIZ_TONE,
    STAGE_CONFIRM,
    STAGE_DETAIL,
    STAGE_GATE,
    STAGE_GENRE,
    STAGE_MOOD,
    STAGE_OCCASION,
    STAGE_SEGMENT,
    STAGE_SOUND,
    STAGE_TALK,
    STAGE_THEME,
    STAGE_UNSAID,
    STAGE_VOICE,
    GENRE_LABELS,
    SOUND_LABELS,
    THEME_LABELS,
    VOICE_LABELS,
    WHOM_LABELS,
    MessengerService,
    webhook_secret,
)
from backend.services.rate_limit import limiter
from backend.settings import SITE_URL

UPDATE_TYPES = [
    "bot_started",
    "message_created",
    "message_callback",
    "bot_stopped",
]
STOP_WORDS = {
    "стоп",
    "stop",
    "отписка",
    "отписаться",
    "не пишите",
    "не пиши",
    "unsubscribe",
}
START_WORDS = {"/start", "start", "начать", "старт"}
GREETING_WORDS = {
    "привет",
    "здравствуй",
    "здравствуйте",
    "хай",
    "hello",
    "hi",
    "добрый",
    "добрый день",
    "добрый вечер",
}
ACCEPT_WORDS = {
    "принимаю",
    "принять",
    "поехали",
    "хочу услышать",
    "согласен",
    "согласна",
    "ок",
    "хорошо",
}
NUDGE_TEXTS = (
    "Твоя песня всё ещё здесь. Превью — минута, и услышишь оба варианта.",
    "Если готов — студия открыта. Бриф на месте.",
    "Если пока не время — не страшно. Бриф остаётся здесь, вернёшься, когда захочется.",
)
NUDGE_BUTTONS = ("Создать сейчас", "Дослушать", "Вернуться к своей песне")
READY_LISTEN_TEXT = (
    "Уже готово — два варианта ждут.\n\n"
    "Открой и послушай, как звучит то, что хотели сказать."
)
UNPAID_PREVIEW_TEXT = (
    "Превью послушал, а песню так и не забрал.\n\n"
    "Не то попало? В расширенном режиме можно собрать звучание иначе — "
    "часто именно там получается вещь, которую оставляют себе."
)


def _callback_btn(text: str, payload: str, *, intent: str | None = None) -> dict:
    btn: dict = {"type": "callback", "text": text[:64], "payload": payload[:128]}
    if intent:
        btn["intent"] = intent
    return btn


def _link_btn(text: str, url: str) -> dict:
    return {"type": "link", "text": text[:64], "url": url}


def _legal_buttons(*, returning: bool = False) -> list[list[dict]]:
    del returning
    return [[_callback_btn("  ХОЧУ УСЛЫШАТЬ  ", "accept", intent="positive")]]


def _legal_nav_buttons(slug: str, page: int, total: int) -> list[list[dict]]:
    rows: list[list[dict]] = []
    if page < total:
        rows.append([_callback_btn("Дальше", f"legal:{slug}:{page + 1}")])
    rows.append(
        [
            _callback_btn("Соглашение", "legal:terms:1"),
            _callback_btn("Политика", "legal:privacy:1"),
            _callback_btn("Оферта", "legal:offer:1"),
        ]
    )
    rows.append([_callback_btn("  ХОЧУ УСЛЫШАТЬ  ", "accept", intent="positive")])
    return rows


def _whom_buttons() -> list[list[dict]]:
    return [
        [
            _callback_btn("👩 Моей маме", "whom:mom"),
            _callback_btn("👨 Моему папе", "whom:dad"),
        ],
        [_callback_btn("❤️ Моей половинке", "whom:partner")],
        [
            _callback_btn("🤙 Дружбану", "whom:buddy"),
            _callback_btn("💛 Подругане", "whom:pal"),
        ],
        [
            _callback_btn("✍️ Напишу сам", "whom:write"),
            _callback_btn("🌌 Конкретно никому", "whom:nobody"),
        ],
    ]


def _occasion_buttons() -> list[list[dict]]:
    return [
        [
            _callback_btn("🎂 День рождения", "occasion:birthday"),
            _callback_btn("💍 Годовщина", "occasion:anniversary"),
        ],
        [
            _callback_btn("🎉 Скоро праздник", "occasion:holiday"),
            _callback_btn("🌿 Просто так, без повода", "occasion:just"),
        ],
        [_callback_btn("🤐 Не могу сказать вслух", "occasion:unsaid")],
    ]


def _about_buttons() -> list[list[dict]]:
    return [
        [_callback_btn("✍️ Напишу своими словами", "about:write")],
        [
            _callback_btn("Про любовь", "about:love"),
            _callback_btn("Про случай", "about:story"),
        ],
        [_callback_btn("Про настроение", "about:feeling")],
        [_callback_btn("⏭ Пока без темы", "about:skip")],
    ]


def _theme_buttons() -> list[list[dict]]:
    return _about_buttons()


def _genre_buttons() -> list[list[dict]]:
    return [
        [
            _callback_btn("Поп", "genre:pop"),
            _callback_btn("Рок", "genre:rock"),
            _callback_btn("Реп", "genre:rap"),
        ],
        [
            _callback_btn("Электронная", "genre:electronic"),
            _callback_btn("Ло-фай", "genre:lofi"),
            _callback_btn("Баллада", "genre:ballad"),
        ],
        [_callback_btn("✍️ Своими словами", "genre:write")],
    ]


def _confirm_buttons() -> list[list[dict]]:
    return [
        [_callback_btn("Так, поехали", "confirm:ok")],
        [_callback_btn("Хочу поправить", "confirm:edit")],
    ]


def _edit_buttons() -> list[list[dict]]:
    return [
        [
            _callback_btn("Кому", "edit:whom"),
            _callback_btn("О чём", "edit:about"),
        ],
        [
            _callback_btn("Жанр", "edit:genre"),
            _callback_btn("Настроение", "edit:mood"),
            _callback_btn("Голос", "edit:voice"),
        ],
    ]


def _detail_gift_buttons() -> list[list[dict]]:
    return [
        [_callback_btn("💬 Есть фраза или привычка", "detail:phrase")],
        [_callback_btn("🎬 Есть сцена, момент", "detail:scene")],
        [_callback_btn("⏭ Пока без этого", "detail:skip")],
    ]


def _detail_just_buttons() -> list[list[dict]]:
    return [
        [_callback_btn("✅ Да, есть", "detail:scene")],
        [_callback_btn("⏭ Пропустить", "detail:skip")],
    ]


def _unsaid_buttons() -> list[list[dict]]:
    return [
        [_callback_btn("✍️ Могу написать своими словами", "unsaid:write")],
        [_callback_btn("🤷 Пока не знаю, как назвать", "unsaid:skip")],
    ]


def _sound_buttons() -> list[list[dict]]:
    return [
        [
            _callback_btn("Энергично", "sound:uplifting"),
            _callback_btn("Романтично", "sound:romantic"),
        ],
        [
            _callback_btn("Спокойно", "sound:peaceful"),
            _callback_btn("Меланхолично", "sound:melancholy"),
        ],
        [
            _callback_btn("Эпично", "sound:adventurous"),
            _callback_btn("Вечеринка", "sound:party"),
        ],
        [_callback_btn("✍️ Своими словами", "sound:write")],
    ]


def _voice_buttons() -> list[list[dict]]:
    return [
        [
            _callback_btn("👩‍🎤 Женский", "voice:female"),
            _callback_btn("🧑‍🎤 Мужской", "voice:male"),
        ],
        [
            _callback_btn("👫 Дуэт", "voice:duet"),
            _callback_btn("🎲 На твоё усмотрение", "voice:auto"),
        ],
    ]


def _biz_goal_buttons() -> list[list[dict]]:
    return [
        [_callback_btn("📢 Реклама / бренд", "bizgoal:ads")],
        [_callback_btn("🏢 Корпоратив, праздник компании", "bizgoal:event")],
        [_callback_btn("🎬 Саундтрек к видео", "bizgoal:video")],
        [_callback_btn("↩️ Я вообще-то про личное", "bizgoal:personal")],
    ]


def _biz_detail_buttons() -> list[list[dict]]:
    return [[_callback_btn("⏭️ Пропустить", "bizdetail:skip")]]


def _biz_tone_buttons() -> list[list[dict]]:
    return [
        [
            _callback_btn("⚡ Энергично", "biztone:energy"),
            _callback_btn("🏛 Солидно", "biztone:solid"),
        ],
        [
            _callback_btn("🤝 Дружелюбно", "biztone:friendly"),
            _callback_btn("🌆 Атмосферно", "biztone:atmosphere"),
        ],
    ]


def _cover_url() -> str:
    base = (SITE_URL or "https://sozdaipesnu.ru").rstrip("/")
    return f"{base}/assets/max-cover.jpg"


def _studio_buttons(url: str, label: str = "Вперёд и с песней!") -> list[list[dict]]:
    return [[_link_btn(label, url)]]


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _user_from_update(update: dict) -> tuple[int | None, str, int | None]:
    user = update.get("user") if isinstance(update.get("user"), dict) else {}
    callback = update.get("callback") if isinstance(update.get("callback"), dict) else {}
    cb_user = callback.get("user") if isinstance(callback.get("user"), dict) else {}
    message = update.get("message") if isinstance(update.get("message"), dict) else {}
    sender = message.get("sender") if isinstance(message.get("sender"), dict) else {}
    recipient = message.get("recipient") if isinstance(message.get("recipient"), dict) else {}
    user_id = (
        _as_int(user.get("user_id"))
        or _as_int(cb_user.get("user_id"))
        or _as_int(sender.get("user_id"))
        or _as_int(recipient.get("user_id"))
    )
    name = (
        (user.get("name") or user.get("first_name") or "")
        or (cb_user.get("name") or cb_user.get("first_name") or "")
        or (sender.get("name") or sender.get("first_name") or "")
    )
    chat_id = _as_int(update.get("chat_id")) or _as_int(recipient.get("chat_id"))
    return user_id, str(name or "").strip(), chat_id


def _message_text(update: dict) -> str:
    message = update.get("message") if isinstance(update.get("message"), dict) else {}
    body = message.get("body") if isinstance(message.get("body"), dict) else {}
    return str(body.get("text") or "").strip()


def _is_bot_sender(update: dict) -> bool:
    message = update.get("message") if isinstance(update.get("message"), dict) else {}
    sender = message.get("sender") if isinstance(message.get("sender"), dict) else {}
    return bool(sender.get("is_bot"))


def _is_dialog(update: dict) -> bool:
    message = update.get("message") if isinstance(update.get("message"), dict) else {}
    recipient = message.get("recipient") if isinstance(message.get("recipient"), dict) else {}
    chat_type = str(recipient.get("chat_type") or "").lower()
    if chat_type in {"chat", "channel"}:
        return False
    if update.get("is_channel") is True:
        return False
    return True


def _is_stop(text: str) -> bool:
    return text.lower().strip().strip("/!.") in STOP_WORDS


def _is_start(text: str) -> bool:
    return text.lower().strip().strip("!") in START_WORDS


def _is_accept_text(text: str) -> bool:
    low = text.lower().strip().strip("!.")
    return low in ACCEPT_WORDS or low.startswith("принимаю") or "хочу услышать" in low


def _is_greeting(text: str) -> bool:
    low = text.lower().strip().strip("!.?")
    return low in GREETING_WORDS or low.startswith("привет")


def _join(prefix: str, text: str) -> str:
    prefix = (prefix or "").strip()
    if prefix:
        return f"{prefix}\n\n{text}"
    return text


def _extract_mid(data) -> str:
    if not isinstance(data, dict):
        return ""
    msg = data.get("message")
    if isinstance(msg, dict):
        body = msg.get("body") if isinstance(msg.get("body"), dict) else {}
        mid = (
            msg.get("mid")
            or msg.get("message_id")
            or body.get("mid")
            or body.get("message_id")
        )
        if mid:
            return str(mid)
    return str(data.get("mid") or data.get("message_id") or "")


class MaxBot:
    def __init__(
        self,
        *,
        api: MaxApi | None = None,
        messenger: MessengerService | None = None,
        auth: AuthService | None = None,
    ) -> None:
        self.api = api or MaxApi()
        self.messenger = messenger or MessengerService()
        self.auth = auth or AuthService()
        self._legal_mid: dict[str, str] = {}

    def subscribe_webhook(self) -> None:
        import os

        if os.getenv("PYTEST_CURRENT_TEST"):
            return
        if not self.api.configured():
            log.info("MAX bot: token not set, skip webhook subscribe")
            return
        site = (SITE_URL or "").rstrip("/")
        if not site.lower().startswith("https://"):
            log.warning("MAX bot: SITE_URL is not https, skip webhook subscribe")
            return
        secret = webhook_secret()
        if len(secret) < 5:
            log.warning("MAX bot: webhook secret too short")
            return
        hook_url = f"{site}/api/webhooks/max"
        existing = self.api.list_subscriptions()
        already = False
        for item in existing:
            url = str(item.get("url") or "")
            types = item.get("update_types") or []
            if url == hook_url and set(UPDATE_TYPES).issubset(set(types) or UPDATE_TYPES):
                already = True
            elif url and url != hook_url:
                self.api.unsubscribe(url)
        if already:
            log.info("MAX webhook already subscribed: %s", hook_url)
            return
        if any(str(item.get("url") or "") == hook_url for item in existing):
            self.api.unsubscribe(hook_url)
        ok = self.api.subscribe(url=hook_url, secret=secret, update_types=UPDATE_TYPES)
        if ok:
            log.info("MAX webhook subscribed: %s", hook_url)
        else:
            log.warning("MAX webhook subscribe failed for %s", hook_url)

    def handle_payload(self, payload: dict | list | None) -> None:
        if payload is None:
            return
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    self.handle_update(item)
            return
        if not isinstance(payload, dict):
            return
        if isinstance(payload.get("updates"), list):
            for item in payload["updates"]:
                if isinstance(item, dict):
                    self.handle_update(item)
            return
        self.handle_update(payload)

    def handle_update(self, update: dict) -> None:
        update_type = str(update.get("update_type") or "")
        if update_type in {"bot_stopped", "dialog_removed"}:
            self._on_stopped(update)
            return
        if not _is_dialog(update):
            return
        if update_type == "message_created" and _is_bot_sender(update):
            return
        user_id, name, chat_id = _user_from_update(update)
        if not user_id:
            return
        if not limiter.allow(f"max_wh:{user_id}", limit=30, window_sec=60.0):
            return
        contact = self.messenger.get_or_create_by_max(
            max_user_id=user_id, chat_id=chat_id, name=name
        )
        if update_type == "bot_started":
            self._on_started(contact, name=name)
            return
        if update_type == "message_callback":
            self._on_callback(update, contact, name=name)
            return
        if update_type == "message_created":
            self._on_text(update, contact, name=name)

    def _send(
        self,
        contact: dict,
        text: str,
        buttons: list[list[dict]] | None = None,
        *,
        image_url: str | None = None,
        image_payload: dict | None = None,
        format: str | None = None,
    ) -> str:
        user_id = contact.get("max_user_id")
        if not user_id:
            return ""
        extra: dict = {}
        if format:
            extra["format"] = format
        data = self.api.send_message(
            user_id=user_id,
            text=text,
            buttons=buttons,
            image_url=image_url,
            image_payload=image_payload,
            **extra,
        )
        if not data:
            log.warning("MAX send_message failed for user %s", user_id)
            return ""
        return _extract_mid(data)

    def _drop_legal(self, contact: dict) -> None:
        uid = str(contact.get("max_user_id") or "")
        mid = self._legal_mid.pop(uid, "")
        if not mid:
            return
        deleter = getattr(self.api, "delete_message", None)
        if callable(deleter):
            deleter(mid)

    def _cover_payload(self) -> dict | None:
        getter = getattr(self.api, "get_cover_payload", None)
        if not callable(getter):
            return None
        try:
            payload = getter()
        except Exception:
            log.exception("MAX cover upload failed")
            return None
        return payload if isinstance(payload, dict) else None

    def _on_stopped(self, update: dict) -> None:
        user_id, _, _ = _user_from_update(update)
        if not user_id:
            return
        contact = self.messenger.get_by_max(user_id)
        if contact:
            self.messenger.mark_blocked(contact)

    def _on_started(self, contact: dict, *, name: str) -> None:
        if contact.get("blocked_at"):
            contact = self.messenger.get_or_create_by_max(
                max_user_id=contact["max_user_id"],
                chat_id=contact.get("max_chat_id"),
            )
        if contact.get("stopped_at") and not contact.get("messages_ok"):
            if self.messenger.has_legal(contact):
                contact = self.messenger.resume_messages(contact)
            else:
                self._send_gate(contact)
                return
        contact = self.messenger.reset_song(contact)
        self._send_gate(contact)

    def _send_legal(self, contact: dict, payload: str) -> None:
        parts = payload.split(":")
        slug = parts[1] if len(parts) > 1 else ""
        page = 1
        if len(parts) > 2:
            try:
                page = int(parts[2])
            except ValueError:
                page = 1
        if slug not in {"terms", "privacy", "offer"}:
            self._send_gate(contact)
            return
        text, idx, total = legal_page(slug, page)
        buttons = _legal_nav_buttons(slug, idx, total)
        uid = str(contact.get("max_user_id") or "")
        mid = self._legal_mid.get(uid, "")
        editor = getattr(self.api, "edit_message", None)
        if mid and callable(editor):
            edited = editor(mid, text=text, buttons=buttons)
            if edited:
                return
        new_mid = self._send(contact, text, buttons)
        if new_mid:
            self._legal_mid[uid] = new_mid

    def _send_gate(self, contact: dict) -> None:
        returning = self.messenger.has_legal(contact)
        text = GATE_RETURN_TEXT if returning else GATE_TEXT
        payload = self._cover_payload()
        self._send(
            contact,
            text,
            _legal_buttons(returning=returning),
            image_payload=payload,
            image_url=None if payload else _cover_url(),
            format=GATE_FORMAT or None,
        )

    def _send_whom(self, contact: dict, prefix: str = "") -> None:
        self._send(contact, _join(prefix, WHOM_TEXT), _whom_buttons())

    def _send_occasion(self, contact: dict, prefix: str = "") -> None:
        self._send(contact, _join(prefix, OCCASION_TEXT), _occasion_buttons())

    def _send_theme(self, contact: dict, prefix: str = "") -> None:
        self._send_about(contact, prefix)

    def _send_about(self, contact: dict, prefix: str = "") -> None:
        self._send(contact, _join(prefix, ABOUT_TEXT), _about_buttons())

    def _send_genre(self, contact: dict, prefix: str = "") -> None:
        self._send(contact, _join(prefix, GENRE_TEXT), _genre_buttons())

    def _send_confirm(self, contact: dict, prefix: str = "") -> None:
        recap = human_recap(
            whom=contact.get("brief_whom") or "",
            occasion=contact.get("brief_mood") or "",
            detail=contact.get("brief_detail") or "",
            genre=contact.get("brief_genre") or "",
            sound=contact.get("brief_sound") or "",
            voice=contact.get("brief_voice") or "",
            plot=contact.get("segment") or "gift",
        )
        text = _join(prefix, recap + "\n" + CONFIRM_FOOTER)
        self._send(contact, text, _confirm_buttons())

    def _send_detail(self, contact: dict, prefix: str = "") -> None:
        if is_just_plot(contact.get("brief_whom") or "", contact.get("segment") or ""):
            self._send(contact, _join(prefix, DETAIL_JUST), _detail_just_buttons())
            return
        whom = contact.get("brief_whom") or ""
        self._send(contact, _join(prefix, detail_gift_text(whom)), _detail_gift_buttons())

    def _send_unsaid(self, contact: dict, prefix: str = "") -> None:
        self._send(contact, _join(prefix, UNSAID_TEXT), _unsaid_buttons())

    def _send_sound(self, contact: dict, prefix: str = "") -> None:
        self._send(contact, _join(prefix, SOUND_TEXT), _sound_buttons())

    def _send_voice(self, contact: dict, prefix: str = "") -> None:
        self._send(contact, _join(prefix, VOICE_TEXT), _voice_buttons())

    def _stay(self, contact: dict, extra: str = "") -> None:
        self._continue_funnel(contact, prefix=extra or GREET_STAY_TEXT)

    def _continue_funnel(self, contact: dict, prefix: str = "") -> None:
        stage = contact.get("funnel_stage") or STAGE_GATE
        awaiting = (contact.get("funnel_await") or "").strip()
        if stage == STAGE_GATE:
            self._send_gate(contact)
            return
        if (contact.get("segment") or "") == "business":
            if stage in {STAGE_BIZ_GOAL, STAGE_SEGMENT, STAGE_TALK, STAGE_GATE}:
                self._send(contact, _join(prefix, BIZ_GOAL_TEXT), _biz_goal_buttons())
                return
            if stage == STAGE_BIZ_DETAIL:
                self._send(contact, _join(prefix, BIZ_DETAIL_TEXT), _biz_detail_buttons())
                return
            if stage == STAGE_BIZ_TONE:
                self._send(contact, _join(prefix, BIZ_TONE_TEXT), _biz_tone_buttons())
                return
            self._send_studio(contact)
            return
        if stage in {STAGE_SEGMENT, STAGE_TALK}:
            if awaiting == "whom":
                self._send(contact, _join(prefix, WHOM_WRITE_PROMPT), _whom_buttons())
                return
            self._send_whom(contact, prefix)
            return
        if stage in {STAGE_OCCASION, STAGE_MOOD}:
            self._send_occasion(contact, prefix)
            return
        if stage in {STAGE_THEME, STAGE_ABOUT}:
            if awaiting == "about":
                self._send(contact, _join(prefix, ABOUT_WAIT), _about_buttons())
                return
            self._send_about(contact, prefix)
            return
        if stage == STAGE_GENRE:
            if awaiting == "genre":
                self._send(contact, _join(prefix, GENRE_WAIT), _genre_buttons())
                return
            self._send_genre(contact, prefix)
            return
        if stage == STAGE_CONFIRM:
            self._send_confirm(contact, prefix)
            return
        if stage == STAGE_UNSAID:
            if awaiting == "unsaid":
                self._send(contact, _join(prefix, UNSAID_WAIT), _unsaid_buttons())
                return
            self._send_unsaid(contact, prefix)
            return
        if stage == STAGE_DETAIL:
            if awaiting == "detail":
                self._send(contact, _join(prefix, DETAIL_WAIT), _detail_gift_buttons())
                return
            self._send_detail(contact, prefix)
            return
        if stage == STAGE_SOUND:
            if awaiting == "mood":
                self._send(contact, _join(prefix, "Напиши настроение своими словами."), _sound_buttons())
                return
            self._send_sound(contact, prefix)
            return
        if stage == STAGE_VOICE:
            self._send_voice(contact, prefix)
            return
        if stage == STAGE_BIZ_GOAL:
            self._send(contact, _join(prefix, BIZ_GOAL_TEXT), _biz_goal_buttons())
            return
        if stage == STAGE_BIZ_DETAIL:
            self._send(contact, _join(prefix, BIZ_DETAIL_TEXT), _biz_detail_buttons())
            return
        if stage == STAGE_BIZ_TONE:
            self._send(contact, _join(prefix, BIZ_TONE_TEXT), _biz_tone_buttons())
            return
        self._send_studio(contact)

    def _on_callback(self, update: dict, contact: dict, *, name: str) -> None:
        callback = update.get("callback") if isinstance(update.get("callback"), dict) else {}
        callback_id = str(callback.get("callback_id") or "")
        payload = str(callback.get("payload") or "").strip()
        if callback_id:
            self.api.answer_callback(callback_id)
        if not payload:
            return
        if payload == "accept":
            self._accept(contact, name=name)
            return
        if payload == "resume":
            contact = self.messenger.resume_messages(contact)
            contact = self.messenger.reset_song(contact)
            self._send_gate(contact)
            return
        if payload == "stop_nudge":
            self.messenger.stop(contact)
            self._send(contact, STOP_TEXT)
            return
        if payload.startswith("legal:"):
            self._send_legal(contact, payload)
            return
        if not self.messenger.can_message(contact):
            if self.messenger.has_legal(contact):
                self._send(contact, RESUME_TEXT, [[_callback_btn("Продолжить", "resume")]])
            else:
                self._send_gate(contact)
            return
        if payload.startswith("whom:"):
            self._apply_whom(contact, payload.split(":", 1)[1])
            return
        if payload.startswith("occasion:") or payload.startswith("mood:"):
            self._apply_occasion(contact, payload.split(":", 1)[1])
            return
        if payload.startswith("theme:") or payload.startswith("about:"):
            self._apply_about(contact, payload.split(":", 1)[1])
            return
        if payload.startswith("genre:"):
            self._apply_genre(contact, payload.split(":", 1)[1])
            return
        if payload.startswith("confirm:"):
            self._apply_confirm(contact, payload.split(":", 1)[1])
            return
        if payload.startswith("edit:"):
            self._apply_edit(contact, payload.split(":", 1)[1])
            return
        if payload.startswith("detail:"):
            self._apply_detail(contact, payload.split(":", 1)[1])
            return
        if payload.startswith("unsaid:"):
            self._apply_unsaid(contact, payload.split(":", 1)[1])
            return
        if payload.startswith("sound:"):
            self._apply_sound(contact, payload.split(":", 1)[1])
            return
        if payload.startswith("voice:"):
            self._apply_voice(contact, payload.split(":", 1)[1])
            return
        if payload.startswith("bizgoal:"):
            self._apply_biz_goal(contact, payload.split(":", 1)[1])
            return
        if payload.startswith("bizdetail:"):
            self._apply_biz_detail(contact, payload.split(":", 1)[1])
            return
        if payload.startswith("biztone:"):
            self._apply_biz_tone(contact, payload.split(":", 1)[1])

    def _on_text(self, update: dict, contact: dict, *, name: str) -> None:
        text = _message_text(update)
        if not text:
            return
        if _is_stop(text):
            self.messenger.stop(contact)
            self._send(contact, STOP_TEXT)
            return
        if not self.messenger.can_message(contact):
            if _is_accept_text(text) and not self.messenger.has_legal(contact):
                self._accept(contact, name=name)
                return
            if _is_accept_text(text) or _is_start(text) or text.lower() in {"продолжить"}:
                if self.messenger.has_legal(contact):
                    contact = self.messenger.resume_messages(contact)
                    contact = self.messenger.reset_song(contact)
                    self._send_gate(contact)
                    return
            if self.messenger.has_legal(contact):
                self._send(contact, RESUME_TEXT, [[_callback_btn("Продолжить", "resume")]])
            else:
                self._send_gate(contact)
            return
        if _is_start(text):
            contact = self.messenger.reset_song(contact)
            self._send_gate(contact)
            return
        if _is_accept_text(text) and (contact.get("funnel_stage") or "") in {
            STAGE_GATE,
            STAGE_SEGMENT,
        }:
            self._accept(contact, name=name)
            return
        if _is_greeting(text) and (contact.get("funnel_await") or "") == "":
            self._stay(contact)
            return
        if is_price_question(text):
            self._stay(contact, FAQ_TEXT)
            return
        if looks_business(text) and (contact.get("segment") or "") != "business":
            self._switch_business(contact)
            return
        awaiting = (contact.get("funnel_await") or "").strip()
        if awaiting == "whom":
            self._apply_whom(contact, text)
            return
        if awaiting == "about":
            self._apply_about(contact, text)
            return
        if awaiting == "detail":
            self._apply_detail(contact, text)
            return
        if awaiting == "unsaid":
            self._apply_unsaid(contact, text)
            return
        if awaiting == "genre":
            self._apply_genre(contact, text)
            return
        if awaiting == "mood":
            self._apply_sound(contact, text)
            return
        if awaiting == "biz_detail":
            self._apply_biz_detail(contact, text)
            return
        stage = contact.get("funnel_stage") or STAGE_GATE
        if stage in {STAGE_GATE, STAGE_SEGMENT, STAGE_TALK}:
            self._apply_whom(contact, text)
            return
        if stage in {STAGE_OCCASION, STAGE_MOOD}:
            self._apply_occasion(contact, text)
            return
        if stage in {STAGE_THEME, STAGE_ABOUT}:
            self._apply_about(contact, text)
            return
        if stage == STAGE_GENRE:
            self._apply_genre(contact, text)
            return
        if stage == STAGE_CONFIRM:
            self._apply_confirm(contact, text)
            return
        if stage == STAGE_DETAIL:
            self._apply_detail(contact, text)
            return
        if stage == STAGE_UNSAID:
            self._apply_unsaid(contact, text)
            return
        if stage == STAGE_SOUND:
            self._apply_sound(contact, text)
            return
        if stage == STAGE_VOICE:
            self._apply_voice(contact, text)
            return
        if stage == STAGE_BIZ_GOAL:
            self._apply_biz_goal(contact, text)
            return
        if stage == STAGE_BIZ_DETAIL:
            self._apply_biz_detail(contact, text)
            return
        if stage == STAGE_BIZ_TONE:
            self._apply_biz_tone(contact, text)
            return
        self._send_studio(contact, extra="Черновик на месте.")

    def _accept(self, contact: dict, *, name: str) -> None:
        try:
            user = self.auth.ensure_max_user(
                max_user_id=str(contact["max_user_id"]),
                name=name,
            )
            contact = self.messenger.accept(contact, user_id=user["id"], name=name)
        except Exception:
            log.exception("MAX accept failed")
            self._send(contact, "Не получилось сохранить. Нажмите «Хочу услышать» ещё раз.")
            return
        self._drop_legal(contact)
        self._send_whom(contact)

    def _switch_business(self, contact: dict) -> None:
        contact = self.messenger.set_segment(contact, "business")
        self._send(contact, BIZ_SWITCH_TEXT)
        self._send(contact, BIZ_GOAL_TEXT, _biz_goal_buttons())

    def _apply_whom(self, contact: dict, raw: str) -> None:
        if raw in {"write", "сам"}:
            contact = self.messenger.set_await(contact, "whom")
            self._send(contact, WHOM_WRITE_PROMPT)
            return
        whom, leftover, plot = parse_whom(raw)
        if whom is None:
            self._send_whom(contact, WHOM_RETRY)
            return
        contact = self.messenger.set_whom(contact, whom, detail=leftover, plot=plot)
        if plot == "just":
            self._send_about(contact)
            return
        self._send_occasion(contact, f"Ок, {whom}.")

    def _apply_occasion(self, contact: dict, raw: str) -> None:
        if raw in OCCASION_LABELS:
            mood = OCCASION_LABELS[raw]
            key = raw
        else:
            mood = parse_occasion(raw)
            key = occasion_key_of(mood or "")
        if not mood:
            self._send_occasion(contact, "Напиши повод своими словами — или ткни вариант.")
            return
        contact = self.messenger.set_occasion(contact, mood, occasion_key=key)
        if key == "unsaid":
            self._send_unsaid(contact, "Понимаю. Тогда пойдём мягче.")
            return
        self._send_detail(contact, "Ещё один штрих — живая деталь, и картина соберётся.")

    def _apply_theme(self, contact: dict, raw: str) -> None:
        self._apply_about(contact, raw)

    def _apply_about(self, contact: dict, raw: str) -> None:
        if raw == "write":
            contact = self.messenger.set_await(contact, "about")
            self._send(contact, ABOUT_WAIT)
            return
        if raw in {"love", "story", "feeling"}:
            theme = THEME_LABELS.get(raw, raw)
            contact = self.messenger.set_about(contact, theme)
            self._send_detail(contact, "Хорошо. Если есть сцена или момент — можно добавить.")
            return
        if raw == "skip" or is_skip(raw):
            contact = self.messenger.set_about(contact, "")
            self._send_detail(contact)
            return
        theme = parse_theme(raw)
        if not theme:
            self._send_about(contact)
            return
        contact = self.messenger.set_about(contact, theme)
        self._send_detail(contact, "Хорошо. Если есть сцена или момент — можно добавить.")

    def _apply_detail(self, contact: dict, raw: str) -> None:
        if raw in {"phrase", "scene"}:
            contact = self.messenger.set_await(contact, "detail")
            self._send(contact, DETAIL_WAIT)
            return
        if raw == "skip" or is_skip(raw):
            detail = (contact.get("brief_detail") or "").strip()
            contact = self.messenger.set_detail(contact, detail)
            self._send_genre(contact)
            return
        parsed = parse_detail(raw)
        detail = "" if parsed is None else parsed
        contact = self.messenger.set_detail(contact, detail)
        prefix = "Хорошая деталь." if detail else ""
        self._send_genre(contact, prefix)

    def _apply_unsaid(self, contact: dict, raw: str) -> None:
        if raw == "write":
            contact = self.messenger.set_await(contact, "unsaid")
            self._send(contact, UNSAID_WAIT)
            return
        if raw == "skip" or is_skip(raw):
            contact = self.messenger.set_detail(contact, contact.get("brief_detail") or "")
            self._send_genre(contact, "Это никуда не денется — просто зазвучит иначе.")
            return
        parsed = parse_detail(raw)
        contact = self.messenger.set_detail(contact, parsed or "")
        self._send_genre(contact, "Это никуда не денется — просто зазвучит иначе.")

    def _apply_genre(self, contact: dict, raw: str) -> None:
        if raw == "write":
            contact = self.messenger.set_await(contact, "genre")
            self._send(contact, GENRE_WAIT)
            return
        if raw in GENRE_LABELS:
            genre = GENRE_LABELS[raw]
        else:
            genre = parse_genre(raw)
        if genre is None:
            self._send_genre(contact)
            return
        contact = self.messenger.set_genre(contact, genre or "")
        self._send_sound(contact)

    def _apply_sound(self, contact: dict, raw: str) -> None:
        if raw == "write":
            contact = self.messenger.set_await(contact, "mood")
            self._send(contact, "Напиши настроение своими словами.")
            return
        if raw in SOUND_LABELS:
            sound = SOUND_LABELS[raw]
        else:
            sound = parse_sound(raw)
        if not sound:
            self._send_sound(contact, "Ткни настроение — или напиши своими словами.")
            return
        contact = self.messenger.set_sound(contact, sound)
        self._send_voice(contact, "Последний штрих.")

    def _apply_voice(self, contact: dict, raw: str) -> None:
        if raw in VOICE_LABELS:
            voice = VOICE_LABELS[raw]
        else:
            voice = parse_voice(raw)
        if not voice:
            self._send(contact, VOICE_RETRY_TEXT, _voice_buttons())
            return
        contact = self.messenger.set_voice(contact, voice)
        self._send_confirm(contact)

    def _apply_confirm(self, contact: dict, raw: str) -> None:
        key = (raw or "").strip().lower()
        if key in {"ok", "так", "поехали", "да", "всё так", "все так"}:
            self._send_studio(contact)
            return
        if key in {"edit", "поправить", "хочу поправить"}:
            self._send(contact, "Что поменять?", _edit_buttons())
            return
        self._send_confirm(contact)

    def _apply_edit(self, contact: dict, raw: str) -> None:
        key = (raw or "").strip().lower()
        mapping = {
            "whom": STAGE_TALK,
            "about": STAGE_ABOUT,
            "genre": STAGE_GENRE,
            "mood": STAGE_SOUND,
            "voice": STAGE_VOICE,
        }
        stage = mapping.get(key)
        if not stage:
            self._send(contact, "Что поменять?", _edit_buttons())
            return
        if key == "about" and not is_just_plot(
            contact.get("brief_whom") or "", contact.get("segment") or ""
        ):
            stage = STAGE_OCCASION
        contact = self.messenger.set_stage(contact, stage)
        self._continue_funnel(contact)

    def _apply_biz_goal(self, contact: dict, raw: str) -> None:
        if raw in {"personal", "личное", "не то"}:
            user_id = contact.get("user_id") or ""
            contact = self.messenger.reset_song(contact)
            if user_id:
                contact = self.messenger.accept(contact, user_id=user_id, name="")
            self._send_whom(contact, "Ок, тогда про личное.")
            return
        key = (raw or "").strip().lower()
        goal = BIZ_GOAL_LABELS.get(key, (raw or "").strip())
        if not goal:
            self._send(contact, BIZ_GOAL_TEXT, _biz_goal_buttons())
            return
        contact = self.messenger.set_biz_goal(contact, goal)
        self._send(contact, f"Понял: {goal}. Давай по делу.\n\n{BIZ_DETAIL_TEXT}", _biz_detail_buttons())

    def _apply_biz_detail(self, contact: dict, raw: str) -> None:
        if raw == "skip" or is_skip(raw):
            contact = self.messenger.set_biz_detail(contact, "")
            self._send(contact, BIZ_TONE_TEXT, _biz_tone_buttons())
            return
        parsed = parse_detail(raw) or ""
        contact = self.messenger.set_biz_detail(contact, parsed)
        prefix = f"Держу: {parsed}." if parsed else ""
        self._send(contact, _join(prefix, BIZ_TONE_TEXT), _biz_tone_buttons())

    def _apply_biz_tone(self, contact: dict, raw: str) -> None:
        key = (raw or "").strip().lower()
        tone = BIZ_TONE_LABELS.get(key, (raw or "").strip())
        if not tone:
            self._send(contact, BIZ_TONE_TEXT, _biz_tone_buttons())
            return
        contact = self.messenger.set_biz_tone(contact, tone)
        self._send_studio(contact)

    def _send_studio(self, contact: dict, extra: str = "") -> None:
        if not contact.get("user_id"):
            self._send_gate(contact)
            return
        url = self.messenger.studio_url(contact)
        if (contact.get("segment") or "") == "business":
            text = (
                biz_studio_mirror(
                    contact.get("brief_whom") or "",
                    contact.get("brief_detail") or "",
                    contact.get("brief_mood") or "",
                )
                + "\n\n"
                + STUDIO_CTA
            )
            if extra:
                text = extra + "\n\n" + text
            self.messenger.mark_sent_to_site(contact)
            self._send(
                contact,
                text + "\n\n" + studio_legal_html(),
                _studio_buttons(url),
                format=STUDIO_FORMAT,
            )
            return
        recap = human_recap(
            whom=contact.get("brief_whom") or "",
            occasion=contact.get("brief_mood") or "",
            detail=contact.get("brief_detail") or "",
            genre=contact.get("brief_genre") or "",
            sound=contact.get("brief_sound") or "",
            voice=contact.get("brief_voice") or "",
            plot=contact.get("segment") or "gift",
        )
        text = recap + "\n\n" + STUDIO_CTA
        if extra:
            text = extra + "\n\n" + text
        self.messenger.mark_sent_to_site(contact)
        self._send(
            contact,
            text + "\n\n" + studio_legal_html(),
            _studio_buttons(url),
            format=STUDIO_FORMAT,
        )

    def process_due_nudges(self, *, limit: int = 20) -> int:
        sent = 0
        for contact in self.messenger.list_due_nudges(limit=limit):
            if not self.messenger.can_message(contact):
                self.messenger.delay_nudge(contact, minutes=60)
                continue
            if not contact.get("user_id") or not contact.get("max_user_id"):
                continue
            step = int(contact.get("nudge_step") or 0)
            if step < 0 or step > 2:
                continue
            text = NUDGE_TEXTS[step]
            whom = (contact.get("brief_whom") or "").strip()
            detail = (contact.get("brief_detail") or "").strip()
            if step == 0 and whom:
                text = (
                    f"Твоя песня {whom} всё ещё здесь. "
                    "Превью — минута, и услышишь оба варианта."
                )
            elif step == 1 and detail:
                text = (
                    f"Та деталь про «{detail}» — она реально делает песню другой. "
                    "Если готов — студия открыта."
                )
            url = self.messenger.studio_url(contact)
            label = NUDGE_BUTTONS[step]
            buttons = _studio_buttons(url, label)
            if step == 2:
                buttons = buttons + [[_callback_btn("Стоп", "stop_nudge")]]
            ok = self.api.send_message(
                user_id=contact["max_user_id"],
                text=text,
                buttons=buttons,
            )
            if ok:
                self.messenger.advance_nudge(contact)
                sent += 1
            else:
                self.messenger.delay_nudge(contact, minutes=15)
                log.warning(
                    "MAX nudge send failed for user %s step %s",
                    contact.get("max_user_id"),
                    step,
                )
        return sent

    def process_due_followups(self, *, limit: int = 20) -> int:
        sent = 0
        for job in self.messenger.list_due_followups(limit=limit):
            contact = self.messenger.get_by_id(job.get("contact_id") or "")
            if not contact or not self.messenger.can_message(contact):
                self.messenger.cancel_followup(job["id"])
                continue
            gen = self.messenger.generation_followup_state(job.get("generation_id") or "")
            if not gen or (gen.get("status") or "") != "success":
                self.messenger.cancel_followup(job["id"])
                continue
            if int(gen.get("purchased") or 0):
                self.messenger.cancel_followup(job["id"])
                continue
            kind = job.get("kind") or ""
            if kind == "ready_listen":
                if gen.get("previewed_at"):
                    self.messenger.cancel_followup(job["id"])
                    continue
                if self.messenger.site_is_recent(contact, minutes=3):
                    self.messenger.delay_followup(job["id"], minutes=5)
                    continue
                text = READY_LISTEN_TEXT
                buttons = [[
                    _link_btn(
                        "Слушать",
                        self.messenger.studio_url(contact, open_to="listen"),
                    )
                ]]
            elif kind == "unpaid_preview":
                if self.messenger.site_is_recent(contact, minutes=3):
                    self.messenger.delay_followup(job["id"], minutes=30)
                    continue
                text = UNPAID_PREVIEW_TEXT
                buttons = [
                    [_link_btn(
                        "Забрать песню",
                        self.messenger.studio_url(contact, open_to="listen"),
                    )],
                    [_link_btn(
                        "Расширенный режим",
                        self.messenger.studio_url(contact, open_to="expert"),
                    )],
                ]
            else:
                self.messenger.cancel_followup(job["id"])
                continue
            ok = self.api.send_message(
                user_id=contact["max_user_id"],
                text=text,
                buttons=buttons,
            )
            if ok:
                self.messenger.mark_followup_sent(job["id"])
                sent += 1
            else:
                self.messenger.delay_followup(job["id"], minutes=15)
        return sent
