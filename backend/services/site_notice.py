"""Плашка на главной: технические работы. Включает владелец из админки."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.logger import log
from backend.settings import DATA_DIR

NOTICE_PATH = DATA_DIR / "site_notice.json"
DEFAULT_TITLE = "Ведутся технические работы"
DEFAULT_TEXT = (
    "Просим немного подождать. Извиняемся за временные неудобства."
)
TITLE_MAX = 120
TEXT_MAX = 500


def _defaults() -> dict[str, Any]:
    return {"on": False, "title": DEFAULT_TITLE, "text": DEFAULT_TEXT}


def get_notice() -> dict[str, Any]:
    path = Path(NOTICE_PATH)
    if not path.is_file():
        return _defaults()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.warning("site notice file unreadable")
        return _defaults()
    if not isinstance(data, dict):
        return _defaults()
    title = str(data.get("title") or "").strip()[:TITLE_MAX] or DEFAULT_TITLE
    text = str(data.get("text") or "").strip()[:TEXT_MAX] or DEFAULT_TEXT
    return {"on": bool(data.get("on")), "title": title, "text": text}


def set_notice(*, on: bool, title: str = "", text: str = "") -> dict[str, Any]:
    notice = {
        "on": bool(on),
        "title": (title or "").strip()[:TITLE_MAX] or DEFAULT_TITLE,
        "text": (text or "").strip()[:TEXT_MAX] or DEFAULT_TEXT,
    }
    path = Path(NOTICE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(notice, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return notice
