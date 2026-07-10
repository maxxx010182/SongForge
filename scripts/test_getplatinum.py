#!/usr/bin/env python3
"""Проверка GetPlatinum init-payment-url из .env. Запуск: ./venv/bin/python scripts/test_getplatinum.py"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.settings import (  # noqa: E402
    GETPLATINUM_ACCOUNT,
    GETPLATINUM_API_KEY,
    GETPLATINUM_VAT,
    PAYMENT_PROVIDER,
    SITE_URL,
)


def main() -> int:
    print("GetPlatinum из .env:")
    print(f"  PAYMENT_PROVIDER={PAYMENT_PROVIDER!r}")
    print(f"  GETPLATINUM_ACCOUNT={GETPLATINUM_ACCOUNT!r}")
    print(f"  GETPLATINUM_API_KEY={'set' if GETPLATINUM_API_KEY else 'EMPTY'}")
    print(f"  SITE_URL={SITE_URL!r}")

    if (PAYMENT_PROVIDER or "").strip().lower() != "getplatinum":
        print("FAIL: PAYMENT_PROVIDER должен быть getplatinum")
        return 1

    if not GETPLATINUM_API_KEY or not GETPLATINUM_ACCOUNT:
        print("FAIL: не заданы GETPLATINUM_API_KEY / GETPLATINUM_ACCOUNT")
        return 1

    account = GETPLATINUM_ACCOUNT.strip().lower().removesuffix(".getplatinum.ru")
    url = f"https://{account}.getplatinum.ru/api/public/pay/init-payment-url"
    payload = {
        "dealId": str(uuid.uuid4()),
        "currency": "RUB",
        "amount": 299,
        "positions": [
            {
                "name": "Тест SongForge — 1 нота",
                "price": 299,
                "quantity": 1,
                "vat": GETPLATINUM_VAT,
            }
        ],
        "clientParams": {
            "clientId": "test-user",
            "email": "test@example.com",
            "name": "Test",
        },
        "notificationUrl": f"{SITE_URL}/api/payment/webhook/getplatinum",
        "successUrl": f"{SITE_URL}/?payment=success",
        "failUrl": f"{SITE_URL}/?payment=failed",
        "customParams": {"package_id": "notes_1", "notes": 1},
    }

    print(f"\nPOST {url}")
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {GETPLATINUM_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        data = response.json() if response.content else {}
    except requests.RequestException as exc:
        print(f"FAIL: сеть — {exc}")
        return 1

    print(f"HTTP {response.status_code}")
    print(f"Ответ: {data}")

    if response.status_code >= 400:
        print("FAIL: HTTP ошибка от GetPlatinum")
        return 1

    error_code = data.get("errorCode")
    if error_code not in (None, 0, "0"):
        print(f"FAIL: errorCode={error_code}")
        return 1

    form_url = data.get("formUrl") or data.get("paymentUrl") or data.get("url")
    if not form_url:
        print("FAIL: нет formUrl / paymentUrl / url в ответе")
        return 1

    print(f"OK: formUrl получен\n  {form_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())