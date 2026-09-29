"""Один сигнал, что текстовая модель сломалась.

Админка читает файл. В MAX уходит одно сообщение на сбой и одно, когда снова
заработало. Повтор той же поломки не шлётся чаще чем раз в три часа.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.logger import log
from backend.settings import ADMIN_MAX_USER_ID, DATA_DIR, MAX_BOT_TOKEN

_LOCK = threading.Lock()
_PATH = DATA_DIR / "llm_signal.json"
_COOLDOWN = timedelta(hours=3)
_RECOVERY_VISIBLE = timedelta(hours=2)

_REASONS = {
    "gone": "модель недоступна",
    "maintenance": "обслуживание",
    "timeout": "нет ответа",
    "other": "ошибка ответа",
}


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


def _notify(text: str) -> None:
    if not ADMIN_MAX_USER_ID or not MAX_BOT_TOKEN:
        return
    try:
        from backend.services.max_api import MaxApi

        api = MaxApi()
        if not api.configured():
            return
        api.send_message(user_id=ADMIN_MAX_USER_ID, text=text[:3500])
    except Exception:
        log.exception("LLM signal: MAX notify failed")


def record_backup_used(
    *,
    provider: str,
    model: str,
    reason: str,
    saved_by: str,
) -> None:
    reason_ru = _REASONS.get(reason, _REASONS["other"])
    message = (
        f"Текст: {provider} {model} не отвечает ({reason_ru}). "
        f"Песню пишет {saved_by}."
    )
    _record(level="warning", message=message, fingerprint=f"down:{provider}:{model}:{reason}")


def record_all_failed(*, provider: str, model: str, reason: str) -> None:
    reason_ru = _REASONS.get(reason, _REASONS["other"])
    message = (
        f"Тексты не пишутся. Последний сбой: {provider} {model} ({reason_ru}). "
        "Песню не запускаем, попытка возвращается."
    )
    _record(level="critical", message=message, fingerprint=f"all:{provider}:{model}:{reason}")


def record_recovery(*, provider: str, model: str) -> None:
    now = _now()
    with _LOCK:
        data = _load()
        if not data.get("open"):
            return
        message = f"Текст снова пишется: {provider} {model}."
        data.update(
            {
                "open": False,
                "level": "warning",
                "message": message,
                "recovered_at": now.isoformat(),
                "last_event_at": now.isoformat(),
            }
        )
        try:
            _save(data)
        except OSError:
            log.exception("LLM signal: save failed")
            return
    _notify(message)


def current_alert() -> dict[str, str] | None:
    data = _load()
    if not data.get("message"):
        return None
    now = _now()
    if data.get("open"):
        return {"level": str(data.get("level") or "warning"), "message": str(data["message"])}
    recovered = _parse(data.get("recovered_at"))
    if recovered and now - recovered <= _RECOVERY_VISIBLE:
        return {"level": "warning", "message": str(data["message"])}
    return None


def _record(*, level: str, message: str, fingerprint: str) -> None:
    now = _now()
    notify = False
    with _LOCK:
        data = _load()
        last = _parse(data.get("last_notified_at"))
        same = data.get("fingerprint") == fingerprint and data.get("open")
        escalated = level == "critical" and data.get("level") != "critical"
        if not same or escalated or last is None or now - last >= _COOLDOWN:
            notify = True
        data.update(
            {
                "open": True,
                "level": level,
                "message": message,
                "fingerprint": fingerprint,
                "since": data.get("since") if same else now.isoformat(),
                "last_event_at": now.isoformat(),
                "recovered_at": None,
            }
        )
        if notify:
            data["last_notified_at"] = now.isoformat()
        try:
            _save(data)
        except OSError:
            log.exception("LLM signal: save failed")
            return
    if notify:
        _notify(message)
