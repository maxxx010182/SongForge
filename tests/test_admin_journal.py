"""Админка: черновик, нота, выкуп песни и оплаты пакетов."""

import uuid

from backend.database.db import get_connection, init_db
from backend.services.admin_service import (
    AdminService,
    present_generation,
    present_payment,
)


def test_generation_labels_for_draft_ready_and_error():
    draft = present_generation(
        {
            "status": "planned",
            "task_id": "",
            "note_charged": 0,
            "purchased": 0,
            "display_name": "DETOX",
            "email": "",
            "user_id": "afa77c4c-1111",
            "fail_msg": None,
        }
    )
    assert draft["kind"] == "Черновик"
    assert draft["note_label"] == "нет"
    assert draft["song_label"] == "нет"
    assert draft["who"] == "DETOX"
    assert draft["fail_msg"] == ""

    ready = present_generation(
        {
            "status": "success",
            "task_id": "abc123",
            "note_charged": 1,
            "purchased": 1,
            "display_name": "",
            "email": "",
            "user_id": "",
            "fail_msg": "",
        }
    )
    assert ready["kind"] == "Готово"
    assert ready["note_label"] == "списана"
    assert ready["song_label"] == "выкуплена"
    assert ready["who"] == ""

    trial_buy = present_generation(
        {
            "status": "success",
            "task_id": "abc",
            "note_charged": 0,
            "purchased": 1,
            "display_name": "",
            "email": "a@b.c",
            "user_id": "u1",
            "fail_msg": "",
        }
    )
    assert trial_buy["note_label"] == "нет"
    assert trial_buy["song_label"] == "выкуплена"
    assert trial_buy["who"] == "a@b.c"

    broken = present_generation(
        {
            "status": "error",
            "task_id": "t1",
            "note_charged": 0,
            "purchased": 0,
            "fail_msg": "  Suno timeout  ",
        }
    )
    assert broken["kind"] == "Ошибка"
    assert broken["fail_msg"] == "Suno timeout"


def test_payment_labels():
    paid = present_payment(
        {
            "status": "paid",
            "display_name": "DETOX",
            "email": "",
            "user_id": "afa77c4c",
        }
    )
    assert paid["pay_label"] == "оплачено"
    assert paid["who"] == "DETOX"
    pending = present_payment({"status": "pending", "display_name": "", "email": "", "user_id": ""})
    assert pending["pay_label"] == "не закончена"
    assert pending["who"] == ""


def test_admin_lists_generation_and_payment_rows():
    init_db()
    user_id = f"adm-{uuid.uuid4()}"
    gen_id = f"gen-{uuid.uuid4()}"
    pay_id = f"pay-{uuid.uuid4()}"
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, balance, created_at)
            VALUES (?, '', 'Журнал', 0, '2026-10-07T10:00:00')
            """,
            (user_id,),
        )
        conn.execute(
            """
            INSERT INTO generations (
                id, created_at, status, title, user_id, task_id,
                purchased, note_charged, fail_msg
            ) VALUES (?, '2026-10-07T10:00:00', 'planned', 'Черновик теста', ?, '', 0, 0, '')
            """,
            (gen_id, user_id),
        )
        conn.execute(
            """
            INSERT INTO payment_orders (
                id, user_id, package_id, notes_amount, price_rub, status, created_at
            ) VALUES (?, ?, 'notes_1', 1, 149, 'pending', '2026-10-07T10:05:00')
            """,
            (pay_id, user_id),
        )
    try:
        gens = AdminService().list_generations(status="planned", limit=200)
        row = next(item for item in gens if item["id"] == gen_id)
        assert row["kind"] == "Черновик"
        assert row["who"] == "Журнал"
        assert row["note_label"] == "нет"
        pays = AdminService().list_payments(limit=200)
        pay = next(item for item in pays if item["id"] == pay_id)
        assert pay["pay_label"] == "не закончена"
        assert pay["notes_amount"] == 1
        assert pay["price_rub"] == 149
        assert pay["who"] == "Журнал"
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM payment_orders WHERE id = ?", (pay_id,))
            conn.execute("DELETE FROM generations WHERE id = ?", (gen_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
