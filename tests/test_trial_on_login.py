"""Пробная генерация: вариант 3 — на аккаунт + браузер после реальной пробной."""

import uuid

from backend.database.db import get_connection, init_db
from backend.services.generation_quota_service import GenerationQuotaService
from backend.services.guest_service import GuestService


def _insert_user(*, user_id: str, trial_used: int = 0) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, balance, created_at, trial_generations_used)
            VALUES (?, ?, ?, 0, datetime('now'), ?)
            """,
            (user_id, f"{user_id}@test.local", f"tester_{user_id[:8]}", trial_used),
        )


def test_switch_account_without_trial_keeps_free_attempt():
    init_db()
    guest = GuestService()
    quota = GenerationQuotaService()
    guest_id = guest.new_guest_id()
    second_user = str(uuid.uuid4())

    _insert_user(user_id=str(uuid.uuid4()), trial_used=0)
    _insert_user(user_id=second_user, trial_used=0)

    # variant 3: выход без использованной пробной — mark_exhausted не вызывается
    quota.sync_guest_trial_on_login(guest_id=guest_id, user_id=second_user)

    assert quota.user_trial_remaining(second_user) == 1


def test_switch_account_after_trial_blocks_free_attempt():
    init_db()
    guest = GuestService()
    quota = GenerationQuotaService()
    guest_id = guest.new_guest_id()
    first_user = str(uuid.uuid4())
    second_user = str(uuid.uuid4())

    _insert_user(user_id=first_user, trial_used=1)
    _insert_user(user_id=second_user, trial_used=0)

    if quota.user_trial_used(first_user) > 0:
        guest.mark_exhausted(guest_id)
    quota.sync_guest_trial_on_login(guest_id=guest_id, user_id=second_user)

    assert quota.user_trial_remaining(second_user) == 0


def test_same_account_has_no_trial_after_use():
    init_db()
    quota = GenerationQuotaService()
    user_id = str(uuid.uuid4())

    _insert_user(user_id=user_id, trial_used=1)

    assert quota.user_trial_remaining(user_id) == 0