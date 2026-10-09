"""Короткое сообщение в техбот. Токен в лог не пишем."""

from __future__ import annotations

import requests

from backend.logger import log
from backend.settings import TELEGRAM_ALERT_BOT_TOKEN, TELEGRAM_ALERT_CHAT_ID


def send_alert(text: str) -> bool:
    token = TELEGRAM_ALERT_BOT_TOKEN
    chat_id = TELEGRAM_ALERT_CHAT_ID
    body = (text or "").strip()
    if not token or not chat_id or not body:
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": body[:3500],
                "disable_web_page_preview": True,
            },
            timeout=5,
        )
    except Exception:
        log.warning("Telegram alert: no answer")
        return False
    if response.status_code != 200:
        log.warning("Telegram alert: HTTP %s", response.status_code)
        return False
    try:
        payload = response.json()
    except ValueError:
        log.warning("Telegram alert: bad answer")
        return False
    if not payload.get("ok"):
        log.warning("Telegram alert: rejected")
        return False
    return True
