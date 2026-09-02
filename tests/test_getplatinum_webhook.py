"""Проверка подписи webhook GetPlatinum (API v2 X-Checksum)."""

from __future__ import annotations

import hmac
import hashlib
from unittest.mock import patch

from backend.services.payment_service import PaymentService


def _hmac_hex_upper(key: str, body: bytes) -> str:
    return hmac.new(key.encode("utf-8"), body, hashlib.sha256).hexdigest().upper()


def test_x_checksum_header_official_v2():
    body = b'{"dealId":"abc","isSuccess":true,"paymentData":{"amount":14900}}'
    key = "TestApiKey"
    header = _hmac_hex_upper(key, body)
    svc = PaymentService()
    with patch("backend.services.payment_service.GETPLATINUM_API_KEY", key):
        assert svc._verify_x_checksum_header(body, header) is True
        assert svc._verify_x_checksum_header(body, header.lower()) is True
        assert svc._verify_x_checksum_header(b'{"tampered":true}', header) is False
        assert svc._verify_x_checksum_header(body, "") is False


def test_gp_receipt_email_required_by_docs():
    uid = "user-1"
    assert PaymentService._gp_receipt_email(
        user_id=uid, user_email="", receipt_email="a@b.ru"
    ) == "a@b.ru"
    assert PaymentService._gp_receipt_email(
        user_id=uid, user_email="real@mail.ru", receipt_email=""
    ) == "real@mail.ru"
    fallback = PaymentService._gp_receipt_email(
        user_id=uid, user_email="", receipt_email=""
    )
    assert fallback.endswith("@users.sozdaipesnu.ru")


def test_user_status_message_has_no_env_secrets():
    msg = PaymentService._status_message("getplatinum", None)
    assert ".env" not in msg
    assert "API" not in msg
    assert "prefix" not in msg.lower()
    assert "support@sozdaipesnu.ru" in msg


def test_webhook_accepts_x_checksum_without_ip_fallback():
    body = b'{"dealId":"abc","isSuccess":true,"notificationType":1,"paymentData":{"amount":14900}}'
    key = "TestApiKey"
    header = _hmac_hex_upper(key, body)
    svc = PaymentService()
    with patch("backend.services.payment_service.GETPLATINUM_API_KEY", key):
        ok = svc.verify_getplatinum_webhook(
            body,
            {"dealId": "abc", "isSuccess": True, "notificationType": 1, "paymentData": {"amount": 14900}},
            client_ip="1.2.3.4",
            checksum_header=header,
        )
        assert ok is True


