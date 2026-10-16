"""Три случая для владельца: нет песни, деньги без нот, ночная копия.

Список читает админка. Письмо уходит на почту поддержки.
Один и тот же случай не пишется чаще раза в три часа.
В текст не попадают почта человека, слова песни и ключи.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.database.db import get_connection
from backend.logger import log
from backend.settings import DATA_DIR

NO_SONG = "no_song"
MONEY = "money_no_notes"
BACKUP = "backup_missed"

NO_SONG_TEXT = "Человек остался без песни. Попытку вернули."
MONEY_TEXT = "Деньги пришли, ноты не начислены."
BACKUP_TEXT = "Ночная копия базы не легла."

_KINDS = {
    NO_SONG: NO_SONG_TEXT,
    MONEY: MONEY_TEXT,
    BACKUP: BACKUP_TEXT,
}
_MAIL_GAP = timedelta(hours=3)
_BACKUP_GAP = timedelta(hours=20)
_FRESH = timedelta(hours=26)
_KEEP = timedelta(days=7)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _ensure(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_events (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            mailed_at TEXT,
            mail_tried_at TEXT
        )
        """
    )


def _safe_message(kind: str, message: str) -> str:
    text = " ".join((message or "").split())
    if not text or "@" in text or len(text) > 200:
        return _KINDS[kind]
    return text


def record(kind: str, message: str) -> None:
    if kind not in _KINDS:
        return
    text = _safe_message(kind, message)
    now = _now()
    try:
        with get_connection() as conn:
            _ensure(conn)
            row = conn.execute(
                """
                SELECT id, message, created_at, mailed_at, mail_tried_at
                FROM owner_events
                WHERE kind = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (kind,),
            ).fetchone()
            if row is not None:
                created = _parse(row["created_at"])
                gap = _BACKUP_GAP if kind == BACKUP else _MAIL_GAP
                same = row["message"] == text
                if created is not None and now - created < gap and (kind == BACKUP or same):
                    event_id = row["id"]
                    mailed = row["mailed_at"]
                    tried = row["mail_tried_at"]
                else:
                    event_id = _insert(conn, kind, text, now)
                    mailed = None
                    tried = None
            else:
                event_id = _insert(conn, kind, text, now)
                mailed = None
                tried = None
    except Exception:
        log.warning("owner event was not saved")
        return
    _maybe_mail(event_id, kind, text, mailed=mailed, tried=tried, now=now)


def _insert(conn, kind: str, text: str, now: datetime) -> str:
    event_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO owner_events (id, kind, message, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (event_id, kind, text, now.isoformat()),
    )
    return event_id


def _maybe_mail(
    event_id: str,
    kind: str,
    text: str,
    *,
    mailed: str | None,
    tried: str | None,
    now: datetime,
) -> None:
    if mailed:
        return
    tried_at = _parse(tried)
    if tried_at is not None and now - tried_at < _MAIL_GAP:
        return
    try:
        with get_connection() as conn:
            _ensure(conn)
            last = conn.execute(
                """
                SELECT mail_tried_at FROM owner_events
                WHERE kind = ? AND mail_tried_at IS NOT NULL
                ORDER BY mail_tried_at DESC
                LIMIT 1
                """,
                (kind,),
            ).fetchone()
            last_at = _parse(last["mail_tried_at"]) if last else None
            if last_at is not None and now - last_at < _MAIL_GAP:
                return
            conn.execute(
                "UPDATE owner_events SET mail_tried_at = ? WHERE id = ?",
                (now.isoformat(), event_id),
            )
    except Exception:
        log.warning("owner event mail mark failed")
        return
    if not _deliver(text):
        return
    try:
        with get_connection() as conn:
            conn.execute(
                "UPDATE owner_events SET mailed_at = ? WHERE id = ?",
                (_now().isoformat(), event_id),
            )
    except Exception:
        log.warning("owner event mail time was not saved")


def _deliver(text: str) -> bool:
    try:
        from backend.services.email_service import EmailService

        return EmailService().send_owner_note(text)
    except Exception:
        log.warning("owner note was not sent")
        return False


def recent(limit: int = 15) -> list[dict[str, str]]:
    cutoff = (_now() - _KEEP).isoformat()
    try:
        with get_connection() as conn:
            _ensure(conn)
            rows = conn.execute(
                """
                SELECT kind, message, created_at
                FROM owner_events
                WHERE created_at >= ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (cutoff, int(limit)),
            ).fetchall()
    except Exception:
        log.warning("owner events were not read")
        return []
    return [
        {
            "kind": str(row["kind"]),
            "message": str(row["message"]),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]


def watch_backup() -> None:
    """Воркер. Молчит, пока ночная копия свежая."""
    now = _now()
    status = _read_status(DATA_DIR / "backup_status.json")
    if status is not None:
        fresh = bool(status["ok"]) and now - status["at"] < _FRESH
    else:
        newest = _newest_local_backup()
        if newest is None:
            return
        fresh = now - newest < _FRESH
    if fresh:
        return
    record(BACKUP, BACKUP_TEXT)


def _read_status(path: Path) -> dict | None:
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    at = _parse(str(data.get("at") or ""))
    if at is None:
        return None
    return {"ok": bool(data.get("ok")), "at": at}


def _newest_local_backup() -> datetime | None:
    folder = Path(os.environ.get("SONGFORGE_BACKUP_DIR", "/root/backups/songforge"))
    if not folder.is_dir():
        return None
    newest: datetime | None = None
    try:
        paths = list(folder.glob("songforge_*.db"))
    except OSError:
        return None
    for path in paths:
        try:
            stamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        except OSError:
            continue
        if newest is None or stamp > newest:
            newest = stamp
    return newest
