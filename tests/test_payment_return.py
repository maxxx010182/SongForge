"""Возврат после оплаты на ту же песню: ссылка кассы и id генерации."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from backend.database.db import get_connection, init_db
from backend.models import CreatePaymentOrderRequest
from backend.services.cabinet_service import CabinetService
from backend.services.payment_service import PaymentService


def test_sanitize_generation_id_accepts_uuid():
    gid = "11111111-2222-3333-4444-555555555555"
    assert PaymentService.sanitize_generation_id(gid) == gid


def test_sanitize_generation_id_rejects_injection_and_timestamp():
    assert PaymentService.sanitize_generation_id("x&other=evil") is None
    assert PaymentService.sanitize_generation_id("javascript:alert(1)") is None
    assert PaymentService.sanitize_generation_id("../etc/passwd") is None
    assert PaymentService.sanitize_generation_id("1234567890123") is None
    assert PaymentService.sanitize_generation_id("") is None
    assert PaymentService.sanitize_generation_id(None) is None


def test_return_urls_append_generation():
    gid = "11111111-2222-3333-4444-555555555555"
    with patch("backend.services.payment_service.SITE_URL", "https://sozdaipesnu.ru"):
        success, fail = PaymentService.return_urls("ord-1", gid)
    assert success == (
        "https://sozdaipesnu.ru/?payment=success&order=ord-1&g=" + gid
    )
    assert fail == "https://sozdaipesnu.ru/?payment=failed&g=" + gid


def test_return_urls_without_generation():
    with patch("backend.services.payment_service.SITE_URL", "https://sozdaipesnu.ru"):
        success, fail = PaymentService.return_urls("ord-1", None)
    assert success == "https://sozdaipesnu.ru/?payment=success&order=ord-1"
    assert fail == "https://sozdaipesnu.ru/?payment=failed"
    assert "g=" not in success
    assert "g=" not in fail


def test_create_order_request_accepts_generation_id():
    req = CreatePaymentOrderRequest(
        package_id="notes_1",
        generation_id="11111111-2222-3333-4444-555555555555",
    )
    assert req.package_id == "notes_1"
    assert req.generation_id.endswith("555555555555")


def test_user_owns_generation():
    init_db()
    cabinet = CabinetService()
    user_id = "user-claim-test"
    gen_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO generations (
                id, created_at, status, user_id, title
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (gen_id, "2026-10-17T12:00:00", "success", user_id, "Тест"),
        )
    try:
        assert cabinet.user_owns_generation(user_id, gen_id) is True
        assert cabinet.user_owns_generation(user_id, str(uuid.uuid4())) is False
        assert cabinet.user_owns_generation("other-user", gen_id) is False
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM generations WHERE id = ?", (gen_id,))
