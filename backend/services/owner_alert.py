"""Телефон владельцу, когда человек остаётся без песни.

Текст песни, почта и ключи сюда не попадают.
Одинаковое сообщение не чаще раза в три часа.
Сбой самой текстовой модели идёт через llm_signal: там уже есть пауза и красная полоска.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.database.db import get_connection
from backend.logger import log
from backend.services.telegram_alert import send_alert
from backend.settings import DATA_DIR

_LOCK = threading.Lock()
_PATH = DATA_DIR / "owner_alert.json"
_COOLDOWN = timedelta(hours=3)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _load() -> dict[str, Any]:
    try:
        if not _PATH.is_file():
            return {}
        data = json.loads(_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_PATH)


def ping(text: str, *, fingerprint: str) -> bool:
    key = (fingerprint or "").strip() or "other"
    now = _now()
    with _LOCK:
        data = _load()
        sent = data.get("sent")
        if not isinstance(sent, dict):
            sent = {}
        last = _parse(str(sent.get(key) or ""))
        if last is not None and now - last < _COOLDOWN:
            return False
        if not send_alert(text):
            return False
        sent[key] = now.isoformat()
        data["sent"] = sent
        try:
            _save(data)
        except OSError:
            log.warning("owner alert: save failed")
        return True


def stuck_count(minutes: int = 10) -> int:
    cutoff = (_now() - timedelta(minutes=minutes)).isoformat()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM generations
            WHERE status = 'generating' AND created_at < ?
            """,
            (cutoff,),
        ).fetchone()
    return int(row["c"]) if row else 0


def watch_stuck() -> None:
    """Раз в полминуты из worker. Молчит, пока песни не висят дольше 10 минут."""
    try:
        count = stuck_count()
    except Exception:
        log.warning("owner alert: stuck check failed")
        return
    with _LOCK:
        open_now = bool(_load().get("stuck_open"))
    if count > 0:
        if ping(
            f"Песня висит дольше 10 минут: {count}. Откройте админку.",
            fingerprint="stuck",
        ):
            _set_stuck_open(True)
        return
    if not open_now:
        return
    ping("Зависших песен больше нет.", fingerprint="stuck-clear")
    _set_stuck_open(False)


def _set_stuck_open(open_now: bool) -> None:
    with _LOCK:
        data = _load()
        data["stuck_open"] = open_now
        try:
            _save(data)
        except OSError:
            log.warning("owner alert: save failed")
