"""Тесты prepaid-режима: полные треки без повторного списания."""

import uuid

from backend.database.db import get_connection, init_db
from backend.models import TrackVariant
from backend.services.cabinet_service import CabinetService
from backend.services.generation_quota_service import GenerationQuotaService


def test_consume_on_start_marks_note_charged_when_production_id_known():
    init_db()
    quota = GenerationQuotaService()
    production_id = f"test-{uuid.uuid4()}"

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, balance, trial_generations_used, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("user-prepaid", "prepaid@test.local", 2, 1, "2026-07-05T12:00:00"),
        )
        conn.execute(
            """
            INSERT INTO generations (
                id, created_at, status, user_id, title
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (production_id, "2026-07-05T12:00:00", "generating", "user-prepaid", "Test"),
        )

    balance = quota.consume_on_start(
        mode="paid",
        user={"id": "user-prepaid", "balance": 2},
        guest_id="",
        production_id=production_id,
    )

    with get_connection() as conn:
        row = conn.execute(
            "SELECT note_charged, balance FROM generations g "
            "JOIN users u ON u.id = g.user_id WHERE g.id = ?",
            (production_id,),
        ).fetchone()

    assert balance == 1
    assert int(row["note_charged"]) == 1

    with get_connection() as conn:
        conn.execute("DELETE FROM generations WHERE id = ?", (production_id,))
        conn.execute("DELETE FROM users WHERE id = ?", ("user-prepaid",))


def test_complete_prepaid_sets_purchased_without_second_charge():
    init_db()
    cabinet = CabinetService()
    production_id = f"test-{uuid.uuid4()}"

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, balance, trial_generations_used, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("user-lib", "lib@test.local", 1, 1, "2026-07-05T12:00:00"),
        )
        conn.execute(
            """
            INSERT INTO generations (
                id, created_at, status, note_charged, purchased, user_id, title,
                music_url_a, music_url_b, lyrics, style
            ) VALUES (?, ?, ?, 1, 0, ?, ?, ?, ?, ?, ?)
            """,
            (
                production_id,
                "2026-07-05T12:00:00",
                "success",
                "user-lib",
                "Paid Song",
                "https://cdn.example/a.mp3",
                "https://cdn.example/b.mp3",
                "[Verse]\nTest",
                "pop",
            ),
        )

    assert cabinet.complete_prepaid_generation(production_id) is True

    with get_connection() as conn:
        gen = conn.execute(
            "SELECT purchased FROM generations WHERE id = ?",
            (production_id,),
        ).fetchone()
        user = conn.execute(
            "SELECT balance FROM users WHERE id = ?",
            ("user-lib",),
        ).fetchone()
        lib_count = conn.execute(
            "SELECT COUNT(*) AS c FROM user_library WHERE generation_id = ?",
            (production_id,),
        ).fetchone()["c"]

    assert int(gen["purchased"]) == 1
    assert int(user["balance"]) == 1
    assert lib_count == 2

    with get_connection() as conn:
        conn.execute("DELETE FROM user_library WHERE generation_id = ?", (production_id,))
        conn.execute("DELETE FROM generations WHERE id = ?", (production_id,))
        conn.execute("DELETE FROM users WHERE id = ?", ("user-lib",))