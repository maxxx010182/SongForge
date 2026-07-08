"""Тесты проверки подписи Telegram Login Widget."""

import hashlib
import hmac
import time

import pytest

from backend.services.telegram_auth import verify_telegram_login


def _make_payload(*, bot_token: str, telegram_id: int = 123456789) -> dict:
    auth_date = int(time.time())
    data = {
        "id": telegram_id,
        "first_name": "Test",
        "username": "testuser",
        "auth_date": auth_date,
    }
    check_lines = [f"{key}={data[key]}" for key in sorted(data.keys())]
    check_string = "\n".join(check_lines)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    data["hash"] = hmac.new(
        secret_key, check_string.encode(), hashlib.sha256
    ).hexdigest()
    return data


def test_verify_telegram_login_ok():
    token = "123456:ABC-DEF"
    payload = _make_payload(bot_token=token)
    result = verify_telegram_login(payload=payload, bot_token=token)
    assert result["telegram_id"] == "123456789"
    assert result["username"] == "testuser"


def test_verify_telegram_login_bad_hash():
    token = "123456:ABC-DEF"
    payload = _make_payload(bot_token=token)
    payload["hash"] = "deadbeef"
    with pytest.raises(ValueError, match="Подпись Telegram"):
        verify_telegram_login(payload=payload, bot_token=token)


def test_verify_telegram_login_expired():
    token = "123456:ABC-DEF"
    payload = _make_payload(bot_token=token)
    payload["auth_date"] = int(time.time()) - 90000
    with pytest.raises(ValueError, match="устарела"):
        verify_telegram_login(payload=payload, bot_token=token)