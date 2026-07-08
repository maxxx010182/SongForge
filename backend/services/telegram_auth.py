"""Проверка подписи Telegram Login Widget."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any


def verify_telegram_login(*, payload: dict[str, Any], bot_token: str) -> dict[str, Any]:
    """https://core.telegram.org/widgets/login#checking-authorization"""
    if not bot_token:
        raise ValueError("Telegram bot token не настроен")

    data = {k: v for k, v in payload.items() if v is not None and v != ""}
    received_hash = str(data.pop("hash", "")).strip()
    if not received_hash:
        raise ValueError("Некорректные данные Telegram")

    auth_date = int(data.get("auth_date") or 0)
    if auth_date <= 0:
        raise ValueError("Некорректная дата авторизации Telegram")
    if time.time() - auth_date > 86400:
        raise ValueError("Сессия Telegram устарела — войдите снова")

    check_lines = [f"{key}={data[key]}" for key in sorted(data.keys())]
    check_string = "\n".join(check_lines)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed = hmac.new(
        secret_key, check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        raise ValueError("Подпись Telegram не прошла проверку")

    telegram_id = str(data.get("id", "")).strip()
    if not telegram_id:
        raise ValueError("Telegram ID обязателен")

    return {
        "telegram_id": telegram_id,
        "first_name": str(data.get("first_name") or "").strip(),
        "last_name": str(data.get("last_name") or "").strip(),
        "username": str(data.get("username") or "").strip(),
        "photo_url": str(data.get("photo_url") or "").strip(),
    }