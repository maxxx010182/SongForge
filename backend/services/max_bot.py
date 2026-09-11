"""Воронка бота MAX: ворота согласий → кому → настроение → ссылка в студию."""

from __future__ import annotations

from backend.logger import log
from backend.services.auth_service import AuthService
from backend.services.max_api import MaxApi
from backend.services.messenger_service import (
    BIZ_GOAL_LABELS,
    BIZ_TONE_LABELS,
    OCCASION_LABELS,
    STAGE_BIZ_GOAL,
    STAGE_BIZ_TONE,
    STAGE_GATE,
    STAGE_MOOD,
    STAGE_SEGMENT,
    STAGE_STOPPED,
    STAGE_TALK,
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
    "согласен",
    "согласна",
    "ок",
    "хорошо",
}
LATER_WORDS = {
    "пока слушаю",
    "пока смотрю",
    "позже",
    "потом",
    "не сейчас",
}

GATE_TEXT = (
    "Есть вещи, которые открыткой не скажешь. Песня — скажет.\n\n"
    "Первая проба бесплатно: два варианта, минут пять.\n\n"
    "«Поехали» — соглашение и политика, как на сайте. Редкие сообщения сюда. "
    "Стоп — напишите «стоп»."
)
SEGMENT_TEXT = "Эта песня — близкому человеку или для дела?"
WHOM_TEXT = "Кому эта песня?"
MOOD_TEXT = "Повод какой? День рождения, просто так, или дата на носу?"
BIZ_WORDS = {
    "business",
    "бизнес",
    "дела",
    "бренд",
    "реклама",
    "джингл",
    "корпоратив",
}
BIZ_GOAL_TEXT = "Для чего трек?"
BIZ_TONE_TEXT = "Как должен звучать бренд в песне?"
LATER_TEXT = (
    "Без имени тоже можно. Чаще дарят маме или любимым — "
    "ткните, слова потом поправим."
)
STOP_TEXT = (
    "Ок, молчу. Если передумаете — напишите сюда. "
    "Документы и данные: support@sozdaipesnu.ru"
)
RESUME_TEXT = "Снова на связи. Продолжим?"


def _callback_btn(text: str, payload: str) -> dict:
    return {"type": "callback", "text": text[:64], "payload": payload[:128]}


def _link_btn(text: str, url: str) -> dict:
    return {"type": "link", "text": text[:64], "url": url}


def _legal_buttons() -> list[list[dict]]:
    base = (SITE_URL or "https://sozdaipesnu.ru").rstrip("/")
    return [
        [_callback_btn("Поехали", "accept")],
        [
            _link_btn("Соглашение", f"{base}/legal/terms"),
            _link_btn("Политика", f"{base}/legal/privacy"),
        ],
    ]


def _whom_buttons() -> list[list[dict]]:
    return [
        [
            _callback_btn("Маме", "whom:mom"),
            _callback_btn("Любимой", "whom:her"),
            _callback_btn("Любимому", "whom:him"),
        ],
        [
            _callback_btn("Другу", "whom:friend"),
            _callback_btn("Себе", "whom:self"),
        ],
    ]


def _mood_buttons() -> list[list[dict]]:
    return [
        [
            _callback_btn("День рождения", "mood:birthday"),
            _callback_btn("Просто так", "mood:just"),
        ],
        [_callback_btn("Скоро праздник", "mood:holiday")],
    ]


def _cover_url() -> str:
    base = (SITE_URL or "https://sozdaipesnu.ru").rstrip("/")
    return f"{base}/assets/max-cover.jpg"


def _looks_business(raw: str) -> bool:
    key = (raw or "").strip().lower()
    if key in BIZ_WORDS:
        return True
    return any(word in key for word in ("реклам", "бренд", "джингл", "корпоратив"))


def _segment_buttons() -> list[list[dict]]:
    return [
        [
            _callback_btn("В подарок", "segment:gift"),
            _callback_btn("Для бизнеса", "segment:business"),
        ]
    ]


def _biz_goal_buttons() -> list[list[dict]]:
    return [
        [
            _callback_btn("Реклама", "bizgoal:ads"),
            _callback_btn("Джингл", "bizgoal:jingle"),
        ],
        [
            _callback_btn("Клиенту", "bizgoal:client"),
            _callback_btn("Корпоратив", "bizgoal:event"),
        ],
    ]


def _biz_tone_buttons() -> list[list[dict]]:
    return [
        [
            _callback_btn("Серьёзно", "biztone:serious"),
            _callback_btn("С юмором", "biztone:light"),
        ]
    ]


def _studio_buttons(url: str) -> list[list[dict]]:
    return [[_link_btn("Открыть студию", url)]]


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
    low = text.lower().strip().strip("/!.")
    return low in STOP_WORDS


def _is_start(text: str) -> bool:
    low = text.lower().strip().strip("!")
    return low in START_WORDS


def _is_accept_text(text: str) -> bool:
    low = text.lower().strip().strip("!.")
    return low in ACCEPT_WORDS or low.startswith("принимаю")


def _is_later(text: str) -> bool:
    low = text.lower().strip()
    return low in LATER_WORDS or "пока слушаю" in low


def _is_greeting(text: str) -> bool:
    low = text.lower().strip().strip("!.?")
    return low in GREETING_WORDS or low.startswith("привет")


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
    ) -> None:
        user_id = contact.get("max_user_id")
        if not user_id:
            return
        ok = self.api.send_message(
            user_id=user_id, text=text, buttons=buttons, image_url=image_url
        )
        if not ok:
            log.warning("MAX send_message failed for user %s", user_id)

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
        if self.messenger.can_message(contact):
            self._continue_funnel(contact)
            return
        if self.messenger.has_legal(contact):
            self._send(
                contact,
                RESUME_TEXT,
                [[_callback_btn("Продолжить", "resume")]],
            )
            return
        self._send_gate(contact)

    def _send_gate(self, contact: dict) -> None:
        self._send(contact, GATE_TEXT, _legal_buttons(), image_url=_cover_url())

    def _continue_funnel(self, contact: dict) -> None:
        stage = contact.get("funnel_stage") or STAGE_GATE
        if (contact.get("segment") or "") == "business":
            if stage in {STAGE_GATE, STAGE_SEGMENT, STAGE_BIZ_GOAL}:
                self._send(contact, BIZ_GOAL_TEXT, _biz_goal_buttons())
                return
            if stage == STAGE_BIZ_TONE:
                self._send(contact, BIZ_TONE_TEXT, _biz_tone_buttons())
                return
            self._send_studio(contact)
            return
        if stage in {STAGE_GATE, STAGE_SEGMENT, STAGE_TALK}:
            self._send(contact, WHOM_TEXT, _whom_buttons())
            return
        if stage == STAGE_MOOD:
            self._send(contact, MOOD_TEXT, _mood_buttons())
            return
        if stage == STAGE_BIZ_GOAL:
            self._send(contact, BIZ_GOAL_TEXT, _biz_goal_buttons())
            return
        if stage == STAGE_BIZ_TONE:
            self._send(contact, BIZ_TONE_TEXT, _biz_tone_buttons())
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
            self._continue_funnel(contact)
            return
        if not self.messenger.can_message(contact):
            if self.messenger.has_legal(contact):
                self._send(
                    contact,
                    RESUME_TEXT,
                    [[_callback_btn("Продолжить", "resume")]],
                )
            else:
                self._send_gate(contact)
            return
        if payload.startswith("segment:"):
            self._apply_segment(contact, payload.split(":", 1)[1])
            return
        if payload.startswith("whom:"):
            self._apply_whom(contact, payload.split(":", 1)[1])
            return
        if payload.startswith("mood:"):
            self._apply_mood(contact, payload.split(":", 1)[1])
            return
        if payload.startswith("bizgoal:"):
            self._apply_biz_goal(contact, payload.split(":", 1)[1])
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
                    self._continue_funnel(contact)
                    return
            if self.messenger.has_legal(contact):
                self._send(
                    contact,
                    RESUME_TEXT,
                    [[_callback_btn("Продолжить", "resume")]],
                )
            else:
                self._send_gate(contact)
            return
        if _is_start(text) or _is_greeting(text):
            self._continue_funnel(contact)
            return
        stage = contact.get("funnel_stage") or STAGE_GATE
        if stage in {STAGE_GATE, STAGE_SEGMENT, STAGE_TALK}:
            if _looks_business(text):
                self._apply_segment(contact, "business")
                return
            if _is_later(text):
                self._send(contact, LATER_TEXT, _whom_buttons())
                return
            self._apply_whom(contact, text)
            return
        if stage == STAGE_MOOD:
            self._apply_mood(contact, text)
            return
        if stage == STAGE_BIZ_GOAL:
            self._apply_biz_goal(contact, text)
            return
        if stage == STAGE_BIZ_TONE:
            self._apply_biz_tone(contact, text)
            return
        self._send_studio(contact, extra="Черновик на месте. Ссылка живая.")

    def _accept(self, contact: dict, *, name: str) -> None:
        try:
            user = self.auth.ensure_max_user(
                max_user_id=str(contact["max_user_id"]),
                name=name,
            )
            contact = self.messenger.accept(contact, user_id=user["id"], name=name)
        except Exception:
            log.exception("MAX accept failed")
            self._send(contact, "Не получилось сохранить. Нажмите «Поехали» ещё раз.")
            return
        self._send(contact, WHOM_TEXT, _whom_buttons())

    def _apply_segment(self, contact: dict, raw: str) -> None:
        key = (raw or "").strip().lower()
        if key in {"business", "бизнес", "дела", "бренд", "реклама", "джингл"}:
            segment = "business"
        elif key in {"gift", "подарок", "близкому", "близкий"} or "подар" in key:
            segment = "gift"
        else:
            self._send(contact, SEGMENT_TEXT, _segment_buttons())
            return
        contact = self.messenger.set_segment(contact, segment)
        if segment == "business":
            self._send(contact, BIZ_GOAL_TEXT, _biz_goal_buttons())
            return
        self._send(contact, WHOM_TEXT, _whom_buttons())

    def _apply_whom(self, contact: dict, raw: str) -> None:
        key = (raw or "").strip().lower()
        if key in {"later", "skip"} or _is_later(raw):
            self._send(contact, LATER_TEXT, _whom_buttons())
            return
        if _looks_business(raw):
            self._apply_segment(contact, "business")
            return
        whom = WHOM_LABELS.get(key, (raw or "").strip())
        if not whom:
            self._send(contact, WHOM_TEXT, _whom_buttons())
            return
        contact = self.messenger.set_whom(contact, whom)
        self._send(contact, MOOD_TEXT, _mood_buttons())

    def _apply_mood(self, contact: dict, raw: str) -> None:
        key = (raw or "").strip().lower()
        aliases = {
            "др": "birthday",
            "день рождения": "birthday",
            "просто так": "just",
            "просто": "just",
            "праздник": "holiday",
            "скоро праздник": "holiday",
        }
        mapped_key = key if key in OCCASION_LABELS else aliases.get(key, "")
        if mapped_key:
            mood = OCCASION_LABELS[mapped_key]
            occasion_key = mapped_key
        else:
            mood = (raw or "").strip()
            occasion_key = ""
        if not mood:
            self._send(contact, MOOD_TEXT, _mood_buttons())
            return
        contact = self.messenger.set_mood(contact, mood, occasion_key=occasion_key)
        self._send_studio(contact)

    def _apply_biz_goal(self, contact: dict, raw: str) -> None:
        key = (raw or "").strip().lower()
        goal = BIZ_GOAL_LABELS.get(key, (raw or "").strip())
        if not goal:
            self._send(contact, BIZ_GOAL_TEXT, _biz_goal_buttons())
            return
        contact = self.messenger.set_biz_goal(contact, goal)
        self._send(contact, BIZ_TONE_TEXT, _biz_tone_buttons())

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
        whom = (contact.get("brief_whom") or "").strip()
        mood = (contact.get("brief_mood") or "").strip()
        hold = ", ".join(part for part in (whom, mood) if part)
        url = self.messenger.studio_url(contact)
        lines = []
        if extra:
            lines.append(extra)
        if hold:
            lines.append(f"Держу: {hold}.")
        else:
            lines.append("Держу вашу идею.")
        lines.append(
            "Сейчас открою студию — одна проба, два варианта, минут пять. Я тут."
        )
        self.messenger.mark_sent_to_site(contact)
        self._send(contact, "\n\n".join(lines), _studio_buttons(url))
