#!/usr/bin/env python3
"""Списки моделей по ключу. Сайт не меняет. Ключи не печатает.

KIE: три живых списка имён, без запроса к модели и без списания.
Cloudflare: все текстовые модели каталога, затем короткий запрос.
Отказ «нет на бесплатном тарифе» — PAID. Текст в ответе — FREE.
Прямой Gemini не вызывается.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path("/root/SongForge/.env")
TIMEOUT = 20
PROBE_LIMIT = 45


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


def fetch(url: str, headers: dict, secrets: list[str], body: dict | None = None) -> tuple[int, object, str]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            raw = response.read(2_000_000).decode("utf-8", "replace")
            http = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read(4000).decode("utf-8", "replace")
        http = exc.code
    except Exception as exc:
        return 0, None, f"ERR {type(exc).__name__}: {redact(str(exc), secrets)}"
    try:
        return http, json.loads(raw), ""
    except Exception:
        return http, None, f"HTTP {http} {redact(raw, secrets)}"


def items_of(data: object) -> list:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("data", "result", "models"):
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for nested in ("data", "models", "items"):
                inner = value.get(nested)
                if isinstance(inner, list):
                    return inner
    return []


def model_name(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    for key in ("slug", "id", "name", "model"):
        value = item.get(key)
        if isinstance(value, str) and value.strip() and not _looks_like_uuid(value):
            return value.strip()
    return ""


def _looks_like_uuid(value: str) -> bool:
    hexes = value.replace("-", "")
    return len(value) >= 32 and len(hexes) == len(value.replace("-", "")) and all(
        ch in "0123456789abcdefABCDEF" for ch in hexes
    )


def task_name(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    task = item.get("task") or item.get("task_name") or ""
    if isinstance(task, dict):
        return str(task.get("name") or task.get("id") or "")
    return str(task)


def is_text_model(item: object) -> bool:
    task = task_name(item).lower().replace("_", " ").replace("-", " ")
    return "text generation" in task or task.strip() == "text"


def auth_failed(http: int, detail: str) -> bool:
    if http == 401:
        return True
    if http != 403:
        return False
    lower = detail.lower()
    if "not available" in lower or "free plan" in lower or "paid" in lower:
        return False
    return "invalid" in lower or "authentication" in lower or "unauthorized" in lower or "auth" in lower


def list_kie(label: str, base_url: str, headers: dict, secrets: list[str]) -> None:
    seen: list[str] = []
    url = base_url
    for _ in range(8):
        http, data, detail = fetch(url, headers, secrets)
        if detail and data is None:
            print(f"KIE {label} {detail}", flush=True)
            if auth_failed(http, detail):
                print(f"KIE {label} STOP key rejected", flush=True)
            return
        if auth_failed(http, detail or json.dumps(data)[:180]):
            print(f"KIE {label} HTTP {http} STOP key rejected", flush=True)
            return
        found = items_of(data)
        if not found:
            print(f"KIE {label} HTTP {http} empty", flush=True)
            return
        for item in found:
            name = model_name(item)
            if name and name not in seen:
                seen.append(name)
                print(f"KIE {label} {name}", flush=True)
        last_id = data.get("last_id") if isinstance(data, dict) else ""
        has_more = bool(data.get("has_more")) if isinstance(data, dict) else False
        if not has_more or not last_id:
            break
        joiner = "&" if "?" in base_url else "?"
        url = f"{base_url}{joiner}after_id={urllib.parse.quote(str(last_id))}"
    print(f"KIE {label} count={len(seen)}", flush=True)


def cloudflare_catalog(account: str, headers: dict, secrets: list[str]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    base = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/models/search"
    for page in range(1, 16):
        url = f"{base}?per_page=50&page={page}"
        http, data, detail = fetch(url, headers, secrets)
        if detail and data is None:
            print(f"CF catalog page={page} {detail}", flush=True)
            if auth_failed(http, detail):
                print("CF STOP key rejected", flush=True)
            return found
        batch = items_of(data)
        if page == 1 and batch:
            sample = batch[0]
            if isinstance(sample, dict):
                print("CF item fields", ",".join(sorted(sample.keys())[:12]), flush=True)
        if not batch:
            if page == 1:
                print(f"CF catalog HTTP {http} empty", flush=True)
            break
        added = 0
        for item in batch:
            name = model_name(item)
            task = task_name(item)
            if not name or name in seen:
                continue
            seen.add(name)
            if is_text_model(item):
                found.append((name, task))
                added += 1
        info = data.get("result_info") if isinstance(data, dict) else None
        total = info.get("total_count") if isinstance(info, dict) else None
        print(f"CF catalog page={page} rows={len(batch)} text+={added}", flush=True)
        if isinstance(total, int) and page * 50 >= total:
            break
        if len(batch) < 50:
            break
    return found


def extract_text(data: object) -> str:
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, str):
                        parts.append(part)
                    elif isinstance(part, dict) and isinstance(part.get("text"), str):
                        parts.append(part["text"])
                return "\n".join(parts).strip()
    return ""


def probe_cloudflare(account: str, headers: dict, secrets: list[str], models: list[tuple[str, str]]) -> None:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions"
    free: list[str] = []
    paid: list[str] = []
    empty: list[str] = []
    chosen = models[:PROBE_LIMIT]
    if len(models) > PROBE_LIMIT:
        print(f"CF probe first {PROBE_LIMIT} of {len(models)}", flush=True)
    for name, task in chosen:
        model = name if name.startswith("@") else f"@cf/{name.lstrip('/')}"
        print(f"CF {model} ...", flush=True)
        http, data, detail = fetch(
            url,
            headers,
            secrets,
            {
                "model": model,
                "messages": [{"role": "user", "content": "Ответь одним словом: да"}],
                "stream": False,
                "max_tokens": 16,
                "temperature": 0,
            },
        )
        blob = detail or (json.dumps(data, ensure_ascii=False) if data is not None else "")
        if auth_failed(http, blob):
            print(f"CF {model} HTTP {http} STOP key rejected", flush=True)
            return
        lower = blob.lower()
        text = extract_text(data)
        if text:
            print(f"CF {model} FREE chars={len(text)} text={text[:40]!r}", flush=True)
            free.append(model)
            continue
        if "free plan" in lower or "not available" in lower or ("paid" in lower and http in (400, 403)):
            print(f"CF {model} PAID", flush=True)
            paid.append(model)
            continue
        if http == 200:
            print(f"CF {model} EMPTY task={task}", flush=True)
            empty.append(model)
            continue
        print(f"CF {model} FAIL {redact(blob, secrets)}", flush=True)
    print(f"CF FREE count={len(free)}", flush=True)
    for model in free:
        print(f"FREE {model}", flush=True)
    print(f"CF PAID count={len(paid)}", flush=True)
    for model in paid:
        print(f"PAID {model}", flush=True)
    print(f"CF EMPTY count={len(empty)}", flush=True)


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
    kie = env.get("KIE_API_KEY", "")
    cloudflare = env.get("CLOUDFLARE_API_TOKEN", "")
    account = env.get("CLOUDFLARE_ACCOUNT_ID", "")
    print("model list: names from the key, then a short Cloudflare check", flush=True)
    print("kie_key", "set" if kie else "empty", flush=True)
    print("cloudflare_token", "set" if cloudflare else "empty", flush=True)
    print("cloudflare_account", "set" if account else "empty", flush=True)
    print("gemini skipped", flush=True)

    if kie:
        base = (env.get("KIE_BASE") or "https://api.kie.ai").rstrip("/")
        headers = {"Authorization": f"Bearer {kie}"}
        list_kie("anthropic", f"{base}/anthropic/v1/models", headers, secrets)
        list_kie("openai", f"{base}/openai/v1/models", headers, secrets)
        list_kie("xai", f"{base}/xai/v1/models", headers, secrets)
    if cloudflare and account:
        headers = {"Authorization": f"Bearer {cloudflare}"}
        models = cloudflare_catalog(account, headers, secrets)
        print(f"CF text models count={len(models)}", flush=True)
        probe_cloudflare(account, headers, secrets, models)
    elif cloudflare or account:
        print("CF SKIP need both token and account", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
