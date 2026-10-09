#!/usr/bin/env python3
"""Очередь текста: Сонет, GPT 5.2, Gemini 3.1 Pro, бесплатная Llama. Ключи не печатает."""

from __future__ import annotations

import re
from pathlib import Path

ENV = Path("/root/SongForge/.env")
KIE_CLAUDE_MODELS = "claude-sonnet-5-5"
KIE_MODELS = "gpt-5-2,gemini-3.1-pro"
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
    print("KIE_CLAUDE_MODELS", KIE_CLAUDE_MODELS)
    print("KIE_MODELS", KIE_MODELS)
    print("CLOUDFLARE_MODELS", CLOUDFLARE_MODELS)
    print("DONE")


if __name__ == "__main__":
    main()
