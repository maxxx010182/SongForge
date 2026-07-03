"""Тесты сохранения флагов монетизации при обновлении генерации."""

import uuid

from backend.database.db import get_connection, init_db
from backend.models import ProductionPlan
from backend.services.history import HistoryService


def _minimal_plan() -> ProductionPlan:
    return ProductionPlan(
        genre="Pop",
        subgenre="Modern Pop",
        mood="uplifting",
        explanation_ru="test",
    )


def test_attach_task_preserves_note_charged_and_purchased():
    init_db()
    history = HistoryService()
    production_id = f"test-{uuid.uuid4()}"

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO generations (
                id, created_at, status, note_charged, purchased, user_id, title
            ) VALUES (?, ?, ?, 1, 0, ?, ?)
            """,
            (production_id, "2026-07-03T12:00:00", "planned", "user-test", "Test"),
        )

    plan = _minimal_plan()
    history.attach_task(
        production_id=production_id,
        task_id="task-test-1",
        idea="Идея",
        title="Test Song",
        lyrics="[Verse 1]\nТест",
        style="pop, uplifting",
        plan=plan,
        user_id="user-test",
    )

    with get_connection() as conn:
        row = conn.execute(
            "SELECT note_charged, purchased, status, task_id FROM generations WHERE id = ?",
            (production_id,),
        ).fetchone()

    assert row is not None
    assert int(row["note_charged"]) == 1
    assert int(row["purchased"]) == 0
    assert row["status"] == "generating"
    assert row["task_id"] == "task-test-1"

    with get_connection() as conn:
        conn.execute("DELETE FROM generations WHERE id = ?", (production_id,))


def test_save_production_preserves_note_charged_on_update():
    init_db()
    history = HistoryService()
    production_id = f"test-{uuid.uuid4()}"

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO generations (
                id, created_at, status, note_charged, purchased, user_id, title
            ) VALUES (?, ?, ?, 1, 1, ?, ?)
            """,
            (production_id, "2026-07-03T12:00:00", "generating", "user-test", "Old"),
        )

    plan = _minimal_plan()
    history.save_production(
        production_id=production_id,
        idea="Новая идея",
        optimized_idea="Новая идея",
        plan=plan,
        title="Updated",
        lyrics="[Chorus]\nНовый текст",
        style="rock",
        user_id="user-test",
    )

    with get_connection() as conn:
        row = conn.execute(
            "SELECT note_charged, purchased, title, status FROM generations WHERE id = ?",
            (production_id,),
        ).fetchone()

    assert row is not None
    assert int(row["note_charged"]) == 1
    assert int(row["purchased"]) == 1
    assert row["title"] == "Updated"
    assert row["status"] == "planned"

    with get_connection() as conn:
        conn.execute("DELETE FROM generations WHERE id = ?", (production_id,))