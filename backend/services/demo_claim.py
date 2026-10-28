"""Срок выкупа демо: 14 дней, потом права у сервиса."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

DEMO_CLAIM_DAYS = 14
UNCLAIMED_HOURS = DEMO_CLAIM_DAYS * 24


def _parse_created(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def demo_claim_open(created_at: str, *, now: datetime | None = None) -> bool:
    """Пока True, человек ещё может выкупить это демо."""
    created = _parse_created(created_at)
    if created is None:
        return True
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment - created < timedelta(days=DEMO_CLAIM_DAYS)
