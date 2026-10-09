#!/usr/bin/env python3
"""Короткий русский куплет у Gemini 3.8 Flash на Kie. Сайт не меняет. Ключ не печатает.

Поддержка советует эту модель вместо нестабильной 3.1 Pro.
Дверь openai мы уже спрашивали. Здесь она ещё раз и родная дверь Gemini.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

ENV_PATH = Path("/root/SongForge/.env")
TIMEOUT = 45
SYSTEM = "Ты автор русских песен. Пиши только текст песни, без пояснений."
USER = (
    "Напиши куплет и припев на русском для песни маме на день рождения. "
    "8–12 строк. Поставь метки [Куплет] и [Припев]."
)


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret and len(secret) > 6:
            text = text.replace(secret, "***")
    return " ".join(text.split())[:180]


def has_russian(text: str) -> bool:
    return any("а" <= char <= "я" or char == "ё" for char in text.lower())


def post(url: str, body: dict, headers: dict, secrets: list[str]) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            return response.status, response.read(12000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(2000).decode("utf-8", "replace")
    except Exception as exc:
        return 0, f"ERR {type(exc).__name__}: {redact(str(exc), secrets)}"


def text_from_obj(data: object) -> str:
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
    candidates = data.get("candidates")
    if isinstance(candidates, list):
        parts: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content")
            if not isinstance(content, dict):
                continue
            for part in content.get("parts") or []:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
        return "\n".join(parts).strip()
    return ""


def text_from_raw(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            return text_from_obj(json.loads(raw))
        except Exception:
            return ""
    parts: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            found = text_from_obj(json.loads(payload))
        except Exception:
            continue
        if found:
            parts.append(found)
    return "\n".join(parts).strip()


def report(name: str, http: int, raw: str, secrets: list[str], usable: list[str]) -> None:
    text = text_from_raw(raw)
    if text:
        ru = "ru=yes" if has_russian(text) else "ru=no"
        print(f"{name} HTTP {http} OK {ru} chars={len(text)} text={text[:80]!r}", flush=True)
        if has_russian(text) and len(text) >= 40:
            usable.append(name)
        return
    try:
        data = json.loads(raw) if raw.strip().startswith("{") else {}
    except Exception:
        data = {}
    code = data.get("code") if isinstance(data, dict) else ""
    msg = ""
    if isinstance(data, dict):
        msg = str(data.get("msg") or data.get("message") or "")
        error = data.get("error")
        if isinstance(error, dict):
            msg = str(error.get("message") or msg)
            code = error.get("code") or code
    if code or msg:
        print(f"{name} HTTP {http} code={code} msg={redact(msg, secrets)}", flush=True)
        return
    print(f"{name} HTTP {http} {redact(raw, secrets)}", flush=True)


def main() -> None:
    if not ENV_PATH.is_file():
        raise SystemExit(f"Нет файла {ENV_PATH}")
    env = load_env(ENV_PATH)
    kie = env.get("KIE_API_KEY", "")
    secrets = [kie]
    if not kie:
        raise SystemExit("kie_key empty")
    base = (env.get("KIE_BASE") or "https://api.kie.ai").rstrip("/")
    headers = {"Authorization": f"Bearer {kie}", "Content-Type": "application/json"}
    print("flash probe: Gemini 3.8 Flash, site is not changed", flush=True)
    usable: list[str] = []

    chat = {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER},
        ],
        "stream": False,
        "include_thoughts": False,
        "max_tokens": 500,
        "temperature": 0.7,
    }
    for slug in ("gemini-3-8-flash-openai", "gemini-3.8-flash", "gemini-3-8-flash"):
        name = f"Kie chat {slug}"
        print(f"{name} ...", flush=True)
        http, raw = post(f"{base}/{slug}/v1/chat/completions", chat, headers, secrets)
        report(name, http, raw, secrets, usable)

    native = {
        "stream": False,
        "contents": [
            {"role": "user", "parts": [{"text": SYSTEM + "\n\n" + USER}]},
        ],
        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.7},
    }
    native_url = f"{base}/gemini/v1/models/gemini-3-8-flash:streamGenerateContent"
    print("Kie native gemini-3-8-flash ...", flush=True)
    http, raw = post(native_url, native, headers, secrets)
    report("Kie native gemini-3-8-flash", http, raw, secrets, usable)
    if "Kie native gemini-3-8-flash" not in usable and not text_from_raw(raw):
        native["stream"] = True
        print("Kie native stream gemini-3-8-flash ...", flush=True)
        http, raw = post(native_url, native, headers, secrets)
        report("Kie native stream gemini-3-8-flash", http, raw, secrets, usable)

    if usable:
        for name in usable:
            print(f"USABLE {name}", flush=True)
    else:
        print("USABLE none", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
