#!/usr/bin/env python3
"""Коротко проверить ключи текстов. Сами ключи не печатает."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

ENV_PATH = Path("/root/SongForge/.env")
TIMEOUT = 25


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def unique(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        item = item.strip()
        if item and item not in seen:
            seen.append(item)
    return seen


def redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret and len(secret) > 6:
            text = text.replace(secret, "***")
    return text.replace("\n", " ")[:180]


def ask(url: str, body: dict, headers: dict, secrets: list[str]) -> str:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            raw = response.read(1500).decode("utf-8", "replace")
            http = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read(800).decode("utf-8", "replace")
        http = exc.code
    except Exception as exc:
        return f"ERR {type(exc).__name__}: {redact(str(exc), secrets)}"
    try:
        data = json.loads(raw)
    except Exception:
        return f"HTTP {http} {redact(raw, secrets)}"
    if not isinstance(data, dict):
        return f"HTTP {http} {redact(raw, secrets)}"
    text = ""
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            text = message["content"].strip()
    if text:
        return f"HTTP {http} OK text={text[:40]!r}"
    code = data.get("code")
    msg = data.get("msg") or data.get("message") or ""
    if isinstance(msg, dict):
        msg = msg.get("message") or msg.get("error") or ""
    error = data.get("error")
    if isinstance(error, dict):
        msg = error.get("message") or msg
        code = error.get("code") or code
    if code or msg:
        return f"HTTP {http} code={code} msg={redact(str(msg), secrets)}"
    return f"HTTP {http} {redact(raw, secrets)}"


def probe_openai(name: str, url: str, key: str, models: list[str], secrets: list[str]) -> None:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for model in models:
        result = ask(
            url,
            {
                "model": model,
                "messages": [{"role": "user", "content": "Ответь одним словом: работает"}],
                "stream": False,
                "max_tokens": 20,
                "temperature": 0,
            },
            headers,
            secrets,
        )
        print(f"{name} {model} {result}", flush=True)
        if "HTTP 401" in result or "HTTP 403" in result:
            print(f"{name} STOP key rejected", flush=True)
            return


def probe_kie(base: str, key: str, models: list[str], secrets: list[str]) -> None:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {
        "messages": [{"role": "user", "content": "Ответь одним словом: работает"}],
        "stream": False,
        "include_thoughts": False,
        "max_tokens": 20,
        "temperature": 0,
    }
    for model in models:
        result = ask(f"{base}/{model}/v1/chat/completions", body, headers, secrets)
        print(f"Kie {model} {result}", flush=True)
        if "HTTP 401" in result or "HTTP 403" in result:
            print("Kie STOP key rejected", flush=True)
            return


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
    print("gemini_key", "set" if gemini else "empty", flush=True)
    print("cloudflare_token", "set" if cloudflare else "empty", flush=True)
    print("cloudflare_account", "set" if account else "empty", flush=True)
    print("kie_key", "set" if kie else "empty", flush=True)

    if gemini:
        models = unique(
            (env.get("GEMINI_MODELS") or "").split(",")
            + ["gemini-3.1-pro-preview", "gemini-2.5-pro", "gemini-2.5-flash"]
        )
        probe_openai(
            "Gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            gemini,
            models,
            secrets,
        )
    if cloudflare and account:
        models = unique(
            (env.get("CLOUDFLARE_MODELS") or "").split(",")
            + [
                "@cf/moonshotai/kimi-k2.6",
                "@cf/moonshotai/kimi-k2.7-code",
                "@cf/openai/gpt-oss-120b",
            ]
        )
        probe_openai(
            "Cloudflare",
            f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions",
            cloudflare,
            models,
            secrets,
        )
    elif cloudflare or account:
        print("Cloudflare SKIP need both token and account", flush=True)
    if kie:
        base = (env.get("KIE_BASE") or "https://api.kie.ai").rstrip("/")
        models = unique(
            [
                env.get("LLM_MODEL_PRO") or "",
                env.get("LLM_MODEL_LITE") or "",
                "gemini-3.1-pro",
                "gemini-3-pro",
            ]
        )
        probe_kie(base, kie, models, secrets)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
