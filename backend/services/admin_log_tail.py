"""Хвост журналов для админки. Пути фиксированы, ключи из строк вырезаются."""

from __future__ import annotations

import os
import re
from pathlib import Path

_NAMES = (
    ("songforge-out.log", "сайт"),
    ("songforge-error.log", "ошибки сайта"),
    ("songforge-worker-out.log", "воркер"),
    ("songforge-worker-error.log", "ошибки воркера"),
)
_TAIL_BYTES = 256_000
_MAX_LINES = 40
_MAX_CHARS = 200
_KEEP = re.compile(
    r"\[(WARNING|ERROR|CRITICAL)\]|Traceback \(most recent call last\)|"
    r"LlmUnavailable|^(ERROR|CRITICAL):",
    re.I,
)
_SECRET = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._\-]{8,}"
    r"|(?:sk-|apk_|key-)[A-Za-z0-9._\-]{6,}"
    r"|\b(?:api[_-]?key|token|secret|password)\b\s*[=:]\s*\S+"
    r"|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)"
)
_START = "LLM provider:"


def log_dir() -> Path:
    raw = (os.getenv("SONGFORGE_LOG_DIR") or "/root/.pm2/logs").strip()
    return Path(raw)


def redact(line: str) -> str:
    flat = " ".join((line or "").split())
    flat = _SECRET.sub("…", flat)
    if len(flat) > _MAX_CHARS:
        flat = flat[:_MAX_CHARS] + "…"
    return flat


def _tail_text(path: Path) -> str:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - _TAIL_BYTES))
        raw = handle.read(_TAIL_BYTES)
    text = raw.decode("utf-8", errors="replace")
    if size > _TAIL_BYTES:
        cut = text.find("\n")
        if cut >= 0:
            text = text[cut + 1 :]
    return text


def recent_failures() -> dict:
    root = log_dir()
    lines: list[dict[str, str]] = []
    starts = 0
    for name, label in _NAMES:
        path = (root / name).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            continue
        if not path.is_file():
            continue
        try:
            text = _tail_text(path)
        except OSError:
            lines.append({"source": label, "text": "журнал не прочитан"})
            continue
        for raw in text.splitlines():
            if _START in raw:
                starts += 1
                continue
            if not _KEEP.search(raw):
                continue
            cleaned = redact(raw)
            if cleaned:
                lines.append({"source": label, "text": cleaned})
    lines = lines[-_MAX_LINES:]
    return {"lines": lines, "starts_in_tail": starts}
