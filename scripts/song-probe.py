#!/usr/bin/env python3
"""Короткий русский куплет тем же телом запроса, что и сайт. Ключи не печатает.

Одно слово «работает» не доказывает, что модель напишет песню.
Успешный ответ Kie списывает немного кредитов.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

ENV_PATH = Path("/root/SongForge/.env")
TIMEOUT = 40
SYSTEM = "Ты автор русских песен. Пиши только текст песни, без пояснений."
USER = (
    "Напиши куплет и припев на русском для песни маме на день рождения. "
    "8–12 строк. Поставь метки [Куплет] и [Припев]."
)
KIE_MODELS = [
    "gemini-3.1-pro",
    "gemini-3-pro",
    "gemini-3-8-flash-openai",
    "gpt-5-2",
]
GEMINI_MODELS = [
    "gemini-3.1-pro-preview",
    "gemini-3.8-flash",
]
CLOUDFLARE_MODELS = [
    "@cf/google/gemma-4-26b-a4b-it",
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "@cf/zai-org/glm-4.7-flash",
    "@cf/openai/gpt-oss-20b",
    "@cf/qwen/qwen3.8-27b",
]


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
    return text.replace("\n", " ")[:180]


def has_russian(text: str) -> bool:
    for char in text.lower():
        if "а" <= char <= "я" or char == "ё":
            return True
    return False


def extract_text(data: dict) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts: list[str] = []
                for part in content:
                    if isinstance(part, str):
                        parts.append(part)
                    elif isinstance(part, dict) and isinstance(part.get("text"), str):
                        parts.append(part["text"])
                return "\n".join(parts).strip()
    candidates = data.get("candidates")
    if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
        content = candidates[0].get("content")
        if isinstance(content, dict):
            parts = content.get("parts")
            if isinstance(parts, list):
                texts = [
                    part.get("text", "")
                    for part in parts
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                ]
                return "\n".join(texts).strip()
    return ""


def ask(url: str, body: dict, headers: dict, secrets: list[str]) -> tuple[str, str]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            raw = response.read(8000).decode("utf-8", "replace")
            http = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read(800).decode("utf-8", "replace")
        http = exc.code
    except Exception as exc:
        return f"ERR {type(exc).__name__}: {redact(str(exc), secrets)}", ""
    try:
        data = json.loads(raw)
    except Exception:
        return f"HTTP {http} {redact(raw, secrets)}", ""
    if not isinstance(data, dict):
        return f"HTTP {http} {redact(raw, secrets)}", ""
    text = extract_text(data)
    if text:
        ru = "ru=yes" if has_russian(text) else "ru=no"
        return f"HTTP {http} OK {ru} chars={len(text)} text={text[:80]!r}", text
    code = data.get("code")
    msg = data.get("msg") or data.get("message") or ""
    if isinstance(msg, dict):
        msg = msg.get("message") or msg.get("error") or ""
    error = data.get("error")
    if isinstance(error, dict):
        msg = error.get("message") or msg
        code = error.get("code") or code
    if code or msg:
        return f"HTTP {http} code={code} msg={redact(str(msg), secrets)}", ""
    return f"HTTP {http} {redact(raw, secrets)}", ""


def key_rejected(result: str) -> bool:
    if "HTTP 401" in result:
        return True
    lower = result.lower()
    if "HTTP 403" not in result:
        return False
    if "not available" in lower or "free plan" in lower:
        return False
    return "invalid" in lower or "authentication" in lower or "unauthorized" in lower


def probe(name: str, url: str, body: dict, headers: dict, secrets: list[str], usable: list[str]) -> bool:
    print(f"{name} ...", flush=True)
    result, text = ask(url, body, headers, secrets)
    print(f"{name} {result}", flush=True)
    if result.startswith("HTTP") and " OK " in result and has_russian(text) and len(text) >= 40:
        usable.append(name)
    return key_rejected(result)


def openai_body(model: str) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER},
        ],
        "stream": False,
        "max_tokens": 500,
        "temperature": 0.7,
    }


def kie_body(model: str) -> dict:
    body = {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER},
        ],
        "stream": False,
        "include_thoughts": False,
        "max_tokens": 500,
        "temperature": 0.7,
    }
    if "pro" in model:
        body["reasoning_effort"] = "low"
    return body


def main() -> None:
    if not ENV_PATH.is_file():
        raise SystemExit(f"Нет файла {ENV_PATH}")
    env = load_env(ENV_PATH)
    secrets = [
        env.get("GEMINI_API_KEY", ""),
        env.get("CLOUDFLARE_API_TOKEN", ""),
        env.get("CLOUDFLARE_ACCOUNT_ID", ""),
        env.get("KIE_API_KEY", ""),
    ]
    gemini = env.get("GEMINI_API_KEY", "")
    cloudflare = env.get("CLOUDFLARE_API_TOKEN", "")
    account = env.get("CLOUDFLARE_ACCOUNT_ID", "")
    kie = env.get("KIE_API_KEY", "")
    print("song probe: short Russian verse, same request shape as the site", flush=True)
    print("gemini_key", "set" if gemini else "empty", flush=True)
    print("cloudflare_token", "set" if cloudflare else "empty", flush=True)
    print("cloudflare_account", "set" if account else "empty", flush=True)
    print("kie_key", "set" if kie else "empty", flush=True)
    usable: list[str] = []

    if kie:
        base = (env.get("KIE_BASE") or "https://api.kie.ai").rstrip("/")
        headers = {"Authorization": f"Bearer {kie}", "Content-Type": "application/json"}
        for model in KIE_MODELS:
            if probe(f"Kie {model}", f"{base}/{model}/v1/chat/completions", kie_body(model), headers, secrets, usable):
                print("Kie STOP key rejected", flush=True)
                break
    if gemini:
        headers = {"Authorization": f"Bearer {gemini}", "Content-Type": "application/json"}
        url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        for model in GEMINI_MODELS:
            if probe(f"Gemini {model}", url, openai_body(model), headers, secrets, usable):
                print("Gemini STOP key rejected", flush=True)
                break
    if cloudflare and account:
        headers = {"Authorization": f"Bearer {cloudflare}", "Content-Type": "application/json"}
        url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions"
        for model in CLOUDFLARE_MODELS:
            if probe(f"Cloudflare {model}", url, openai_body(model), headers, secrets, usable):
                print("Cloudflare STOP key rejected", flush=True)
                break
    elif cloudflare or account:
        print("Cloudflare SKIP need both token and account", flush=True)

    if usable:
        for name in usable:
            print(f"USABLE {name}", flush=True)
    else:
        print("USABLE none", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
