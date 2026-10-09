#!/usr/bin/env python3
"""Привязать техбот к чату владельца и прислать проверку.

Токен уже лежит в .env. Скрипт читает последнее личное сообщение боту,
записывает TELEGRAM_ALERT_CHAT_ID и шлёт одну фразу. Токен не печатает.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

ENV = Path("/root/SongForge/.env")
TEST_TEXT = (
    "Техбот на связи. Сюда придёт сообщение, если текст песни не соберётся, "
    "музыка не запустится или песня зависнет дольше 10 минут. "
    "На ваши сообщения этот бот не отвечает."
)


def load_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def upsert(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    if pattern.search(text):
        return pattern.sub(line, text, count=1)
    if text and not text.endswith("\n"):
        text += "\n"
    return text + line + "\n"


def call(token: str, method: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Telegram HTTP {exc.code}. Токен в чат не присылайте.")
    except urllib.error.URLError:
        raise SystemExit("Telegram не ответил. Повторите эту строку через минуту.")
    if not isinstance(parsed, dict) or not parsed.get("ok"):
        raise SystemExit("Telegram отклонил запрос. Проверьте токен в .env, в чат его не присылайте.")
    return parsed


def latest_private(updates: list) -> dict | None:
    found: dict | None = None
    stamp = -1
    for item in updates:
        if not isinstance(item, dict):
            continue
        message = item.get("message") or item.get("edited_message")
        if not isinstance(message, dict):
            continue
        chat = message.get("chat")
        if not isinstance(chat, dict) or chat.get("type") != "private":
            continue
        when = int(message.get("date") or 0)
        if when >= stamp:
            stamp = when
            found = message
    return found


def main() -> None:
    if not ENV.is_file():
        raise SystemExit(f"Нет файла {ENV}")
    env = load_env(ENV)
    token = env.get("TELEGRAM_ALERT_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "TOKEN empty. Сначала строка TELEGRAM_ALERT_BOT_TOKEN в .env. Токен в чат не присылайте."
        )
    payload = call(token, "getUpdates", {"timeout": 0, "allowed_updates": ["message"]})
    updates = payload.get("result")
    message = latest_private(updates if isinstance(updates, list) else [])
    if not message:
        raise SystemExit(
            "Нет сообщения боту. Откройте нового техбота, нажмите Start и запустите эту строку снова."
        )
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    chat_id = str(chat.get("id") or "").strip()
    if not chat_id:
        raise SystemExit("Чат не распознан. Нажмите Start ещё раз и повторите строку.")
    text = upsert(ENV.read_text(encoding="utf-8"), "TELEGRAM_ALERT_CHAT_ID", chat_id)
    tmp = ENV.with_suffix(".env.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(ENV)
    call(token, "sendMessage", {"chat_id": chat_id, "text": TEST_TEXT, "disable_web_page_preview": True})
    name = str(sender.get("first_name") or chat.get("first_name") or "").strip()
    username = str(sender.get("username") or "").strip()
    who = name or "чат"
    if username:
        who = f"{who} @{username}"
    print("CHAT", who)
    print("TEST sent")
    print("DONE")


if __name__ == "__main__":
    main()
