"""Вечернее окно дожима: 19:00 по поясу человека, запасной — Москва."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[misc, assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[misc, assignment]

FALLBACK_TZ = "Europe/Moscow"
SEND_HOUR = 19
_TZ_OK = re.compile(r"^[A-Za-z0-9_+\-/]{1,64}$")
_MSK = timezone(timedelta(hours=3))


def normalize_tz(name: str | None) -> str:
    raw = (name or "").strip()
    if not raw or not _TZ_OK.fullmatch(raw):
        return ""
    if ZoneInfo is None:
        return FALLBACK_TZ if raw == FALLBACK_TZ else ""
    try:
        ZoneInfo(raw)
    except (ZoneInfoNotFoundError, Exception):
        return ""
    return raw


def resolve_tz(name: str | None):
    raw = normalize_tz(name) or FALLBACK_TZ
    if ZoneInfo is None:
        return _MSK
    try:
        return ZoneInfo(raw)
    except (ZoneInfoNotFoundError, Exception):
        try:
            return ZoneInfo(FALLBACK_TZ)
        except (ZoneInfoNotFoundError, Exception):
            return _MSK


def evening_after(
    tz_name: str | None,
    *,
    days: int = 1,
    after: datetime | None = None,
) -> str:
    """Локальные 19:00 через `days` календарных дней от `after` (UTC)."""
    tz = resolve_tz(tz_name)
    now = after or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(tz)
    delta = max(int(days), 0)
    target = local.date() + timedelta(days=delta)
    if delta == 0:
        today_send = datetime(
            local.year, local.month, local.day, SEND_HOUR, 0, tzinfo=tz
        )
        if local >= today_send:
            target = local.date() + timedelta(days=1)
    local_send = datetime(target.year, target.month, target.day, SEND_HOUR, 0, tzinfo=tz)
    return local_send.astimezone(timezone.utc).isoformat()
