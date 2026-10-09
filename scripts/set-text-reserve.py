#!/usr/bin/env python3
"""Записать запасные ключи текстов в .env. Сами ключи не печатает."""

from __future__ import annotations

import getpass
import re
from pathlib import Path

ENV = Path("/root/SongForge/.env")


def upsert(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    if pattern.search(text):
        return pattern.sub(line, text, count=1)
    if text and not text.endswith("\n"):
        text += "\n"
    return text + line + "\n"


def clean(value: str) -> str:
    value = value.strip().strip('"').strip("'")
    if any(ch.isspace() for ch in value):
        raise SystemExit("В ключе есть пробел или перенос. Файл не менял.")
    return value


def ask(label: str) -> str:
    print(label)
    print("Вставка не отображается. Вставь и нажми Enter. Пусто — пропустить.")
    return clean(getpass.getpass("> "))


def main() -> None:
    if not ENV.is_file():
        raise SystemExit(f"Нет файла {ENV}")

    gemini = ask("1. Ключ Gemini с https://aistudio.google.com/apikey")
    if not gemini:
        raise SystemExit("Ключ Gemini пустой. Файл не менял.")

    cloudflare = ask("2. Токен Cloudflare. Если его нет — просто Enter.")
    account = ""
    if cloudflare:
        account = ask("3. Account ID Cloudflare, это не токен. Если его нет — Enter.")
        if not account:
            print("Без Account ID Cloudflare не включится. Запишу только Gemini.")
            cloudflare = ""

    text = ENV.read_text(encoding="utf-8")
    text = upsert(text, "GEMINI_API_KEY", gemini)
    text = upsert(text, "GEMINI_MODELS", "gemini-3.1-pro-preview")
    if cloudflare and account:
        text = upsert(text, "CLOUDFLARE_API_TOKEN", cloudflare)
        text = upsert(text, "CLOUDFLARE_ACCOUNT_ID", account)
        text = upsert(text, "CLOUDFLARE_MODELS", "@cf/qwen/qwen3.8-27b")

    tmp = ENV.with_suffix(".env.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(ENV)

    saved: dict[str, str] = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        saved[key.strip()] = value.strip().strip('"').strip("'")
    names = (
        "GEMINI_API_KEY",
        "GEMINI_MODELS",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
    )
    for name in names:
        value = saved.get(name, "")
        if name == "GEMINI_MODELS":
            print(name, value or "empty")
        else:
            print(name, "set" if value else "empty")
    print("Готово. Ключи на экран не выводились.")


if __name__ == "__main__":
    main()
