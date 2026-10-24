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


_TS = re.compile(
    r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[,.]\d+)?\s+"
    r"(?:\[[A-Z]+\]\s+\S+:\s+)?"
)
_EXC = re.compile(r"^[A-Za-z_][\w.]*(?:Error|Exception|Exit):")
_CARET = re.compile(r"^[\s~^]+$")


def _body(raw: str) -> str:
    return _TS.sub("", raw or "").strip()


def explain(text: str) -> str:
    low = text.lower()
    if "address already in use" in low or "errno 98" in low:
        return (
            "При обновлении лишний запуск не занял порт 8000: его уже держит работающий сайт. "
            "Сайт при этом отвечает. Число справа — сколько таких попыток лежит в хвосте журнала."
        )
    return text


def _trace_follow(raw: str) -> bool:
    body = _body(raw)
    if not body:
        return False
    if body.startswith(("File ", "Traceback", "During handling", "The above exception")):
        return True
    if raw[:1] in {" ", "\t"} or _CARET.match(body):
        return True
    return bool(_EXC.match(body))


def _exception_text(block: list[str]) -> str:
    chosen = ""
    for raw in block:
        body = _body(raw)
        if _EXC.match(body):
            chosen = redact(body)
    if not chosen:
        return "В журнале оборванный след ошибки, самой причины в хвосте нет."
    return explain(chosen)


def _collect(label: str, raw_lines: list[str]) -> tuple[list[dict], int]:
    found: list[dict] = []
    starts = 0
    index = 0
    while index < len(raw_lines):
        raw = raw_lines[index]
        if _START in raw:
            starts += 1
            index += 1
            continue
        if raw.strip().startswith("Traceback (most recent call last)"):
            block = [raw]
            index += 1
            while index < len(raw_lines) and _trace_follow(raw_lines[index]):
                block.append(raw_lines[index])
                index += 1
            found.append({"source": label, "text": _exception_text(block)})
            continue
        if not _KEEP.search(raw):
            index += 1
            continue
        cleaned = explain(redact(raw))
        if cleaned:
            found.append({"source": label, "text": cleaned})
        index += 1
    return found, starts


def _fold(rows: list[dict]) -> list[dict]:
    folded: list[dict] = []
    for row in rows:
        if (
            folded
            and folded[-1]["source"] == row["source"]
            and folded[-1]["text"] == row["text"]
        ):
            folded[-1]["count"] += 1
            continue
        folded.append({"source": row["source"], "text": row["text"], "count": 1})
    return folded[-15:]


def recent_failures() -> dict:
    root = log_dir()
    lines: list[dict] = []
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
            lines.append({"source": label, "text": "журнал не прочитан", "count": 1})
            continue
        found, seen = _collect(label, text.splitlines())
        lines.extend(found)
        starts += seen
    return {"lines": _fold(lines), "starts_in_tail": starts}
