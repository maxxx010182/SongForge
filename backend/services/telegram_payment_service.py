"""Telegram-уведомления о бета-заказах: сообщение админу + кнопка «Начислить»."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import requests

from backend.database.db import get_connection
from backend.logger import log
from backend.services.payment_service import PACKAGES, PaymentService
from backend.settings import (
    SITE_URL,
    TELEGRAM_ADMIN_CHAT_IDS,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_PAYMENT_POLLING,
)

CALLBACK_PREFIX = "pc:"
_POLL_THREAD: threading.Thread | None = None
_POLL_STOP = threading.Event()


class TelegramPaymentNotifier:
    def __init__(self, payment_service: PaymentService | None = None) -> None:
        self._payment = payment_service or PaymentService()

    @staticmethod
    def is_enabled() -> bool:
        return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_CHAT_IDS)

    def notify_new_order(
        self,
        *,
        order_id: str,
        package_id: str,
        user_email: str | None,
        display_name: str | None,
        beta_price_rub: int,
    ) -> None:
        if not self.is_enabled():
            return

        package = PACKAGES.get(package_id, {})
        notes = int(package.get("notes") or 0)
        label = package.get("label") or package_id
        email = (user_email or "").strip() or "—"
        name = (display_name or "").strip() or "—"
        short_id = order_id[:8]

        text = (
            "🎵 <b>Новый заказ (бета)</b>\n\n"
            f"Пакет: <b>{label}</b> — {notes} нот\n"
            f"К оплате: <b>{beta_price_rub}₽</b>\n"
            f"Email: <code>{email}</code>\n"
            f"Ник: {name}\n"
            f"Заказ: <code>{order_id}</code>\n\n"
            "После поступления перевода нажмите кнопку ниже."
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": f"✅ Начислить {notes} нот",
                        "callback_data": f"{CALLBACK_PREFIX}{order_id}",
                    }
                ]
            ]
        }

        for chat_id in TELEGRAM_ADMIN_CHAT_IDS:
            self._api(
                "sendMessage",
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )

    def process_update(self, update: dict) -> bool:
        callback = update.get("callback_query")
        if not callback:
            return False

        chat = callback.get("message", {}).get("chat", {})
        chat_id = str(chat.get("id", ""))
        if chat_id not in TELEGRAM_ADMIN_CHAT_IDS:
            self._answer_callback(
                callback["id"],
                "Нет прав для подтверждения оплат",
                alert=True,
            )
            return True

        data = str(callback.get("data") or "")
        if not data.startswith(CALLBACK_PREFIX):
            return False

        order_id = data[len(CALLBACK_PREFIX) :].strip()
        if not order_id:
            self._answer_callback(callback["id"], "Некорректный заказ", alert=True)
            return True

        result = self._confirm_order(order_id=order_id, chat_id=chat_id)
        if not result:
            self._answer_callback(
                callback["id"],
                "Заказ не найден или уже оплачен",
                alert=True,
            )
            return True

        notes = result["notes_added"]
        balance = result["balance"]
        self._answer_callback(callback["id"], f"Начислено {notes} нот")
        message = callback.get("message") or {}
        if message.get("chat") and message.get("message_id"):
            old_text = message.get("text") or message.get("caption") or ""
            new_text = (
                f"{old_text}\n\n"
                f"✅ <b>Начислено {notes} нот</b> (баланс: {balance})\n"
                f"Подтвердил: Telegram {chat_id}"
            )
            self._api(
                "editMessageText",
                chat_id=message["chat"]["id"],
                message_id=message["message_id"],
                text=new_text,
                parse_mode="HTML",
            )
        return True

    def _confirm_order(self, *, order_id: str, chat_id: str) -> dict | None:
        result = self._payment.mark_paid(
            order_id=order_id,
            provider_payment_id=f"telegram:{chat_id}",
        )
        if not result:
            return None

        with get_connection() as conn:
            from backend.services.admin_service import AdminService

            admin_svc = AdminService()
            admin_row = conn.execute(
                """
                SELECT id FROM admin_users
                WHERE role = 'super_admin' AND is_active = 1
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            admin_id = (
                admin_row["id"] if admin_row else f"telegram:{chat_id}"
            )
            admin_svc._write_audit(
                conn,
                admin_user_id=admin_id,
                action="payments.telegram_confirm",
                target_type="payment_order",
                target_id=order_id,
                details={
                    "notes_added": result["notes_added"],
                    "user_id": result["user_id"],
                    "balance": result["balance"],
                    "telegram_chat_id": chat_id,
                },
                ip_address="telegram",
            )
        log.info("Telegram: заказ %s подтверждён chat=%s", order_id[:8], chat_id)
        return result

    def start_background(self) -> None:
        global _POLL_THREAD
        if not self.is_enabled():
            return
        if not TELEGRAM_PAYMENT_POLLING:
            log.info(
                "Telegram: polling выключен — настройте setWebhook на %s/api/telegram/webhook",
                SITE_URL,
            )
            return
        if _POLL_THREAD and _POLL_THREAD.is_alive():
            return

        _POLL_STOP.clear()

        def _loop() -> None:
            offset = 0
            log.info("Telegram: long polling для бета-оплат запущен")
            while not _POLL_STOP.is_set():
                try:
                    resp = self._api_raw(
                        "getUpdates",
                        timeout=35,
                        params={"timeout": 30, "offset": offset},
                    )
                    if not resp or not resp.ok:
                        time.sleep(5)
                        continue
                    for item in resp.json().get("result") or []:
                        offset = int(item["update_id"]) + 1
                        try:
                            self.process_update(item)
                        except Exception as exc:
                            log.info("Telegram update error: %s", exc)
                except Exception as exc:
                    log.info("Telegram polling error: %s", exc)
                    time.sleep(5)

        _POLL_THREAD = threading.Thread(
            target=_loop,
            name="telegram-payment-poll",
            daemon=True,
        )
        _POLL_THREAD.start()

    @staticmethod
    def stop_background() -> None:
        _POLL_STOP.set()

    def _api(self, method: str, **payload: Any) -> dict | None:
        resp = self._api_raw(method, json=payload)
        if not resp:
            return None
        try:
            data = resp.json()
        except json.JSONDecodeError:
            log.info("Telegram %s: невалидный JSON", method)
            return None
        if not data.get("ok"):
            log.info("Telegram %s: %s", method, data.get("description", data))
            return None
        return data.get("result")

    def _api_raw(
        self,
        method: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        timeout: int = 15,
    ) -> requests.Response | None:
        if not TELEGRAM_BOT_TOKEN:
            return None
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
        try:
            return requests.post(
                url,
                params=params,
                json=json,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            log.info("Telegram %s request failed: %s", method, exc)
            return None

    def _answer_callback(
        self,
        callback_id: str,
        text: str,
        *,
        alert: bool = False,
    ) -> None:
        self._api(
            "answerCallbackQuery",
            callback_query_id=callback_id,
            text=text[:200],
            show_alert=alert,
        )