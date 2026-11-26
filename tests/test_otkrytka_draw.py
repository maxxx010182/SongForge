"""Проба открытки: кредит списывается только с готовой картинкой, ноты не трогаем."""

import uuid
from datetime import datetime, timedelta, timezone

from backend.database.db import get_connection, init_db, utc_now
from backend.services.admin_service import AdminService
from backend.services.image_card_service import ImageCardService
from backend.services.image_gate import DAILY, FAILED, NEED_CREDITS

JPEG = b"\xff\xd8\xff" + (b"a" * 9000)


class FakeKie:
    def __init__(self, state="success"):
        self.state = state
        self.created = []

    def configured(self):
        return True

    def create_task(self, prompt):
        self.created.append(prompt)
        return "task-1"

    def read_task(self, task_id):
        return {"state": self.state, "url": "https://cdn.example/card.jpg"}


class FakeStore:
    def __init__(self):
        self.saved = []

    def upload_bytes(self, *, key, data, content_type):
        self.saved.append((key, content_type, data[:3]))
        return "https://files.example/" + key


def _service(state="success"):
    init_db()
    service = ImageCardService()
    kie = FakeKie(state)
    service._kie = kie
    service._storage = FakeStore()
    service._fetch = lambda url: (JPEG, ("jpg", "image/jpeg"))
    return service, kie


def _user(credits, balance=4):
    user_id = f"card-{uuid.uuid4()}"
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (
                id, email, display_name, balance, image_credits, created_at
            ) VALUES (?, '', ?, ?, ?, ?)
            """,
            (user_id, user_id[:12], balance, credits, utc_now()),
        )
    return user_id


def _cleanup(user_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM image_cards WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.execute("DELETE FROM admin_audit_log WHERE target_id = ?", (user_id,))


def _balance(user_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT balance, image_credits FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return int(row["balance"]), int(row["image_credits"])


def test_ready_card_spends_a_credit_and_leaves_song_notes():
    service, kie = _service()
    user_id = _user(1)
    try:
        result = service.draw(user={"id": user_id}, prompt="мама в саду")
        notes, credits = _balance(user_id)
        assert notes == 4
        assert credits == 0
        assert result["card"]["status"] == "ready"
        assert result["card"]["image_url"].startswith("https://files.example/cards/")
        assert kie.created == ["мама в саду"]
        assert service._storage.saved
    finally:
        _cleanup(user_id)


def test_failed_card_returns_the_credit():
    service, kie = _service("fail")
    user_id = _user(1)
    try:
        result = service.draw(user={"id": user_id}, prompt="мама в саду")
        notes, credits = _balance(user_id)
        assert notes == 4
        assert credits == 1
        assert result["card"]["status"] == "failed"
        assert result["card"]["message"] == FAILED
        assert kie.created == ["мама в саду"]
        assert service._storage.saved == []
    finally:
        _cleanup(user_id)


def test_no_credits_does_not_call_out():
    service, kie = _service()
    user_id = _user(0)
    try:
        try:
            service.draw(user={"id": user_id}, prompt="мама в саду")
            raised = False
        except Exception as exc:
            raised = True
            assert exc.status == 403
            assert exc.detail == NEED_CREDITS
        assert raised
        assert kie.created == []
        assert _balance(user_id) == (4, 0)
    finally:
        _cleanup(user_id)


def test_daily_cap_does_not_call_out():
    service, kie = _service()
    user_id = _user(3)
    now = utc_now()
    try:
        with get_connection() as conn:
            for n in range(5):
                conn.execute(
                    """
                    INSERT INTO image_cards (
                        id, user_id, prompt, status, task_id, image_url,
                        credits_spent, created_at, finished_at
                    ) VALUES (?, ?, 'уже', 'failed', '', '', 0, ?, '')
                    """,
                    (f"{user_id}-{n}", user_id, now),
                )
        try:
            service.draw(user={"id": user_id}, prompt="ещё одна")
            raised = False
        except Exception as exc:
            raised = True
            assert exc.detail == DAILY
        assert raised
        assert kie.created == []
        assert _balance(user_id) == (4, 3)
    finally:
        _cleanup(user_id)


def test_stuck_card_without_a_task_returns_the_credit():
    service, _kie = _service()
    user_id = _user(0)
    old = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    card_id = str(uuid.uuid4())
    try:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO image_cards (
                    id, user_id, prompt, status, task_id, image_url,
                    credits_spent, created_at, finished_at
                ) VALUES (?, ?, 'зависла', 'drawing', '', '', 1, ?, '')
                """,
                (card_id, user_id, old),
            )
        service.settle(user_id)
        assert _balance(user_id) == (4, 1)
        row = service._get(card_id)
        assert row["status"] == "failed"
    finally:
        _cleanup(user_id)


def test_admin_grant_changes_credits_only():
    init_db()
    user_id = _user(0, balance=7)
    try:
        result = AdminService().adjust_image_credits(
            admin_id="admin-test",
            admin_role="super_admin",
            target_user_id=user_id,
            delta=3,
            reason="проба",
        )
        assert result["image_credits"] == 3
        assert result["balance"] == 7
        assert _balance(user_id) == (7, 3)
    finally:
        _cleanup(user_id)
