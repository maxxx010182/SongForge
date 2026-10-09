#!/usr/bin/env python3
"""Очередь текста: Gemini 3 Pro, Gemini 3.1 Pro, при ошибке GPT 5.2. Сонет выключен."""

from __future__ import annotations

import re
from pathlib import Path

ENV = Path("/root/SongForge/.env")
KIE_CLAUDE_MODELS = ""
KIE_MODELS = "gemini-3-pro,gemini-3.1-pro,gpt-5-2"
CLOUDFLARE_MODELS = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"


def upsert(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    if pattern.search(text):
        return pattern.sub(line, text, count=1)
    if text and not text.endswith("\n"):
        text += "\n"
    return text + line + "\n"


def main() -> None:
    if not ENV.is_file():
        raise SystemExit(f"Нет файла {ENV}")
    text = upsert(ENV.read_text(encoding="utf-8"), "KIE_CLAUDE_MODELS", KIE_CLAUDE_MODELS)
    text = upsert(text, "KIE_MODELS", KIE_MODELS)
    text = upsert(text, "CLOUDFLARE_MODELS", CLOUDFLARE_MODELS)
    tmp = ENV.with_suffix(".env.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(ENV)
    print("KIE_CLAUDE_MODELS", KIE_CLAUDE_MODELS or "off")
    print("KIE_MODELS", KIE_MODELS)
    print("CLOUDFLARE_MODELS", CLOUDFLARE_MODELS)
    print("DONE")


if __name__ == "__main__":
    main()
