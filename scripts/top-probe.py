#!/usr/bin/env python3
"""Короткий русский куплет у сильных моделей Kie. Сайт не меняет. Ключ не печатает.

Flash не спрашивает. Формат запроса у этих моделей другой, чем у текущего Gemini.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

ENV_PATH = Path("/root/SongForge/.env")
TIMEOUT = 70
SYSTEM = "Ты автор русских песен. Пиши только текст песни, без пояснений."
USER = (
    "Напиши куплет и припев на русском для песни маме на день рождения. "
    "8–12 строк. Поставь метки [Куплет] и [Припев]."
)
CLAUDE = ("claude-fable-5", "claude-opus-5-5", "claude-sonnet-5-5")
GPT = ("gpt-6-astra",)


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
            return response.status, response.read(16000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(2000).decode("utf-8", "replace")
    except Exception as exc:
        return 0, f"ERR {type(exc).__name__}: {redact(str(exc), secrets)}"


def text_from_obj(data: object) -> str:
    if not isinstance(data, dict):
        return ""
    chunks: list[str] = []
    content = data.get("content")
    if isinstance(content, str):
        chunks.append(content)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                chunks.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            inner = item.get("content")
            if isinstance(inner, str):
                chunks.append(inner)
            elif isinstance(inner, list):
                for part in inner:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        chunks.append(part["text"])
    return "\n".join(part.strip() for part in chunks if part and part.strip()).strip()


def report(name: str, http: int, raw: str, secrets: list[str], usable: list[str]) -> bool:
    text = ""
    data: object = None
    if raw.strip().startswith("{"):
        try:
            data = json.loads(raw)
            text = text_from_obj(data)
        except Exception:
            data = None
    if text:
        ru = "ru=yes" if has_russian(text) else "ru=no"
        print(f"{name} HTTP {http} OK {ru} chars={len(text)} text={text[:80]!r}", flush=True)
        if has_russian(text) and len(text) >= 40:
            usable.append(name)
        return False
    code = ""
    msg = ""
    if isinstance(data, dict):
        code = data.get("code") or ""
        msg = str(data.get("msg") or data.get("message") or "")
        error = data.get("error")
        if isinstance(error, dict):
            msg = str(error.get("message") or msg)
            code = error.get("code") or code
    if code or msg:
        print(f"{name} HTTP {http} code={code} msg={redact(str(msg), secrets)}", flush=True)
    else:
        print(f"{name} HTTP {http} {redact(raw, secrets)}", flush=True)
    return http == 404


def claude_body(model: str) -> dict:
    return {
        "model": model,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": USER}],
        "max_tokens": 800,
        "stream": False,
    }


def gpt_body(model: str) -> dict:
    return {
        "model": model,
        "stream": False,
        "max_output_tokens": 800,
        "reasoning": {"effort": "low"},
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": SYSTEM + "\n\n" + USER}],
            }
        ],
    }


def door(url: str) -> str:
    for name in ("anthropic", "claude", "codex", "openai"):
        if f"/{name}/" in url:
            return name
    return "api"


def ask_first_working(
    name: str,
    urls: list[str],
    body: dict,
    headers: dict,
    secrets: list[str],
    usable: list[str],
) -> None:
    print(f"{name} ...", flush=True)
    before = len(usable)
    for url in urls:
        http, raw = post(url, body, headers, secrets)
        missing = report(f"{name} {door(url)}", http, raw, secrets, usable)
        if len(usable) > before or not missing:
            return


def main() -> None:
    if not ENV_PATH.is_file():
        raise SystemExit(f"Нет файла {ENV_PATH}")
    env = load_env(ENV_PATH)
    kie = env.get("KIE_API_KEY", "")
    if not kie:
        raise SystemExit("kie_key empty")
    secrets = [kie]
    base = (env.get("KIE_BASE") or "https://api.kie.ai").rstrip("/")
    headers = {"Authorization": f"Bearer {kie}", "Content-Type": "application/json"}
    print("top probe: Fable, Opus, Sonnet, Astra. Site is not changed", flush=True)
    usable: list[str] = []

    claude_urls = [
        f"{base}/anthropic/v1/messages",
        f"{base}/claude/v1/messages",
    ]
    for model in CLAUDE:
        ask_first_working(f"Claude {model}", claude_urls, claude_body(model), headers, secrets, usable)

    gpt_urls = [
        f"{base}/codex/v1/responses",
        f"{base}/openai/v1/responses",
    ]
    for model in GPT:
        print(f"GPT {model} ...", flush=True)
        before = len(usable)
        for url in gpt_urls:
            http, raw = post(url, gpt_body(model), headers, secrets)
            if http in (400, 422):
                report(f"GPT {model} {door(url)} limited", http, raw, secrets, usable)
                http, raw = post(
                    url,
                    {"model": model, "stream": False, "input": gpt_body(model)["input"]},
                    headers,
                    secrets,
                )
            report(f"GPT {model} {door(url)}", http, raw, secrets, usable)
            if len(usable) > before or http != 404:
                break

    if usable:
        for name in usable:
            print(f"USABLE {name}", flush=True)
    else:
        print("USABLE none", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
