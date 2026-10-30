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
# Первое письмо через час. Ночь 22:00–07:00 не трогаем: ближайшие 10:00.
SOON_HOURS = 1
QUIET_FROM = 22
QUIET_UNTIL = 7
MORNING_HOUR = 10
# Последний день демо — днём, пока срок ещё не вышел.
DAY_LAST_HOUR = 12
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


def clock_on_day(
    tz_name: str | None,
    anchor_iso: str,
    day_num: int,
    hour: int,
) -> str:
    """Локальный час в день `day_num`. Дата якоря — день 1."""
    tz = resolve_tz(tz_name)
    local = _as_utc(anchor_iso).astimezone(tz)
    target = local.date() + timedelta(days=max(int(day_num), 1) - 1)
    local_send = datetime(
        target.year, target.month, target.day, int(hour), 0, tzinfo=tz
    )
    return local_send.astimezone(timezone.utc).isoformat()


def evening_on_day(tz_name: str | None, anchor_iso: str, day_num: int) -> str:
    """19:00 в день `day_num`. Дата якоря — день 1."""
    return clock_on_day(tz_name, anchor_iso, day_num, SEND_HOUR)


def _quiet(moment: datetime) -> bool:
    return moment.hour >= QUIET_FROM or moment.hour < QUIET_UNTIL


def hour_ping(tz_name: str | None, after: datetime | None = None) -> str:
    """Через час, если это дневное время. Иначе ближайшие 10:00 по поясу человека.

    Ночью и если час сам выпадает на 22:00–07:00 — не завтра любой ценой,
    а ближайшее утро. В 6 утра это сегодняшние 10:00.
    """
    tz = resolve_tz(tz_name)
    moment = after or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone(tz)
    send = local + timedelta(hours=SOON_HOURS)
    if _quiet(local) or _quiet(send):
        morning = datetime(
            local.year, local.month, local.day, MORNING_HOUR, 0, tzinfo=tz
        )
        if local >= morning:
            nxt = local.date() + timedelta(days=1)
            morning = datetime(nxt.year, nxt.month, nxt.day, MORNING_HOUR, 0, tzinfo=tz)
        send = morning
    return send.astimezone(timezone.utc).isoformat()


def _append_later(slots: list[str], slot: str) -> None:
    if slots and datetime.fromisoformat(slot) <= datetime.fromisoformat(slots[-1]):
        return
    slots.append(slot)


def studio_slots(tz_name: str | None, anchor_iso: str) -> list[str]:
    """Песню не запустили: через час, следующий вечер, 3-й и 7-й день.

    День ухода — первый. Совпадающие времена не повторяем.
    """
    anchor = _as_utc(anchor_iso)
    first = hour_ping(tz_name, anchor)
    slots = [first]
    nxt = evening_after(tz_name, days=0, after=datetime.fromisoformat(first))
    _append_later(slots, nxt)
    for day_num in (3, 7):
        _append_later(slots, evening_on_day(tz_name, anchor_iso, day_num))
    return slots


def keep_plan(tz_name: str | None, anchor_iso: str) -> list[tuple[str, str]]:
    """Письма, когда песня есть и не куплена. Отсчёт от готовности.

    Дни 1, 4, 7 и 11 — в 19:00. День 14 — в полдень, раньше конца 14 суток.
    Если 19:00 первого дня уже прошло, это письмо уходит следующим вечером.
    """
    from backend.services.demo_claim import DEMO_CLAIM_DAYS

    anchor = _as_utc(anchor_iso)
    expiry = anchor + timedelta(days=DEMO_CLAIM_DAYS)
    slots: list[tuple[str, str]] = []
    for day_num, kind in (
        (1, "keep_d1"),
        (4, "keep_d4"),
        (7, "keep_d7"),
        (11, "keep_d11"),
    ):
        due = evening_on_day(tz_name, anchor_iso, day_num)
        if datetime.fromisoformat(due) <= anchor:
            due = evening_after(tz_name, days=0, after=anchor)
        if slots and datetime.fromisoformat(due) <= datetime.fromisoformat(slots[-1][1]):
            continue
        slots.append((kind, due))
    last = clock_on_day(tz_name, anchor_iso, DEMO_CLAIM_DAYS, DAY_LAST_HOUR)
    last_dt = datetime.fromisoformat(last)
    if last_dt >= expiry:
        last_dt = expiry - timedelta(hours=3)
    if last_dt > anchor and last_dt < expiry:
        if not slots or last_dt > datetime.fromisoformat(slots[-1][1]):
            slots.append(("keep_d14", last_dt.astimezone(timezone.utc).isoformat()))
    return slots


def keep_evenings(tz_name: str | None, anchor_iso: str) -> list[str]:
    """Времена писем про невыкупленную песню, от готовности."""
    return [due for _, due in keep_plan(tz_name, anchor_iso)]
