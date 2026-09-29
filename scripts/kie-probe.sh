#!/bin/bash
# Короткий запрос к нескольким моделям Kie. Ключ читается на сервере и не печатается.
set -u
ENV_FILE="${1:-/root/SongForge/.env}"
if [ ! -f "$ENV_FILE" ]; then
  echo "Нет файла $ENV_FILE"
  exit 1
fi
python3 - "$ENV_FILE" << 'PY'
import json, sys, urllib.error, urllib.request
from pathlib import Path

env = {}
for line in Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    env[key.strip()] = value.strip().strip('"').strip("'")

api_key = env.get("KIE_API_KEY", "")
base = (env.get("KIE_BASE") or "https://api.kie.ai").rstrip("/")
print("provider", env.get("LLM_PROVIDER") or "-")
print("configured_pro", env.get("LLM_MODEL_PRO") or "gemini-2.5-pro")
print("configured_lite", env.get("LLM_MODEL_LITE") or "gemini-2.5-flash")
if not api_key:
    print("NO_KEY")
    sys.exit(1)

slugs = []
for slug in (
    env.get("LLM_MODEL_PRO") or "gemini-2.5-pro",
    env.get("LLM_MODEL_LITE") or "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-3-flash",
    "gemini-3-pro",
    "gemini-3.1-pro",
):
    slug = slug.strip()
    if slug and slug not in slugs:
        slugs.append(slug)

body = json.dumps({
    "messages": [{"role": "user", "content": "Ответь одним словом: работает"}],
    "stream": False,
    "include_thoughts": False,
    "max_tokens": 20,
    "temperature": 0,
}).encode()

for slug in slugs:
    url = f"{base}/{slug}/v1/chat/completions"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            raw = response.read(1200).decode("utf-8", "replace")
            http = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read(800).decode("utf-8", "replace")
        http = exc.code
    except Exception as exc:
        print(f"{slug} ERR {type(exc).__name__}: {exc}")
        continue
    summary = raw.replace("\n", " ")[:220]
    try:
        data = json.loads(raw)
    except Exception:
        data = None
    if isinstance(data, dict):
        msg = data.get("msg") or data.get("message")
        code = data.get("code")
        text = ""
        try:
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, str):
                text = content.strip()
            elif isinstance(content, list):
                text = " ".join(
                    str(block.get("text") or "")
                    for block in content
                    if isinstance(block, dict)
                ).strip()
        except Exception:
            text = ""
        if text:
            print(f"{slug} HTTP {http} OK text={text[:80]!r}")
            continue
        if msg or code not in (None, 200):
            print(f"{slug} HTTP {http} code={code} msg={msg}")
            continue
    print(f"{slug} HTTP {http} body={summary}")
PY
