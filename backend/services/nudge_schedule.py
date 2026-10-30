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


def _as_utc(anchor_iso: str) -> datetime:
    try:
        anchor = datetime.fromisoformat(anchor_iso)
    except ValueError:
        anchor = datetime.now(timezone.utc)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    return anchor


def evening_on_day(tz_name: str | None, anchor_iso: str, day_num: int) -> str:
    """19:00 в день `day_num`. Дата якоря — день 1."""
    tz = resolve_tz(tz_name)
    local = _as_utc(anchor_iso).astimezone(tz)
    target = local.date() + timedelta(days=max(int(day_num), 1) - 1)
    local_send = datetime(
        target.year, target.month, target.day, SEND_HOUR, 0, tzinfo=tz
    )
    return local_send.astimezone(timezone.utc).isoformat()


def _append_later(slots: list[str], slot: str) -> None:
    if slots and datetime.fromisoformat(slot) <= datetime.fromisoformat(slots[-1]):
        return
    slots.append(slot)


def studio_slots(tz_name: str | None, anchor_iso: str) -> list[str]:
    """Четыре вечера, если песню ещё не запустили: ближайший, следующий, 3-й и 7-й.

    День ухода считается первым. Если 19:00 уже прошло, ближайший вечер — завтра.
    Совпадающие даты не повторяем. Письмо через час не ставим.
    """
    anchor = _as_utc(anchor_iso)
    nearest = evening_after(tz_name, days=0, after=anchor)
    slots = [nearest]
    nxt = evening_after(tz_name, days=1, after=datetime.fromisoformat(nearest))
    _append_later(slots, nxt)
    for day_num in (3, 7):
        _append_later(slots, evening_on_day(tz_name, anchor_iso, day_num))
    return slots


def keep_evenings(tz_name: str | None, anchor_iso: str) -> list[str]:
    """Вечера 3, 7, 10 и 14-го дня после готовой песни.

    Отсчёт от готовности, не от прослушивания. Тот же вечер, что и письмо
    «через 5 минут», не дублируем.
    """
    tz = resolve_tz(tz_name)
    anchor = _as_utc(anchor_iso)
    local = anchor.astimezone(tz)
    nearest = datetime.fromisoformat(evening_after(tz_name, days=0, after=anchor))
    slots: list[str] = []
    for day_num in (3, 7, 10, 14):
        target = local.date() + timedelta(days=day_num - 1)
        local_send = datetime(
            target.year, target.month, target.day, SEND_HOUR, 0, tzinfo=tz
        )
        slot = local_send.astimezone(timezone.utc)
        if slot > nearest:
            slots.append(slot.isoformat())
    return slots
