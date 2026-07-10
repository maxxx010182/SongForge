#!/usr/bin/env python3
"""Подбор GETPLATINUM_POSITION_PREFIX перебором 1..40. Только на сервере с .env."""

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
    SITE_URL,
)


def try_prefix(prefix: int) -> tuple[bool, str]:
    account = GETPLATINUM_ACCOUNT.strip().lower().removesuffix(".getplatinum.ru")
    url = f"https://{account}.getplatinum.ru/api/public/pay/init-payment-url"
    payload = {
        "dealId": str(uuid.uuid4()),
        "currency": "RUB",
        "amount": 299,
        "positions": [
            {
                "prefix": prefix,
                "name": "Тест SongForge — 1 нота",
                "price": 299,
                "quantity": 1,
                "vat": GETPLATINUM_VAT,
            }
        ],
        "clientParams": {
            "clientId": "probe",
            "email": "probe@example.com",
            "name": "Probe",
        },
        "notificationUrl": f"{SITE_URL}/api/payment/webhook/getplatinum",
        "successUrl": f"{SITE_URL}/?payment=success",
        "failUrl": f"{SITE_URL}/?payment=failed",
    }
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {GETPLATINUM_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        data = response.json() if response.content else {}
    except requests.RequestException as exc:
        return False, f"net: {exc}"

    if response.status_code >= 400:
        err = data.get("errorMessage") or data
        return False, f"HTTP {response.status_code}: {err}"

    if data.get("errorCode") not in (None, 0, "0"):
        return False, f"errorCode={data.get('errorCode')}: {data.get('errorMessage')}"

    if data.get("formUrl") or data.get("paymentUrl"):
        return True, "formUrl OK"

    return False, f"no formUrl: {data}"


def main() -> int:
    if not GETPLATINUM_API_KEY or not GETPLATINUM_ACCOUNT:
        print("FAIL: нет GETPLATINUM_API_KEY / GETPLATINUM_ACCOUNT в .env")
        return 1

    print(f"Перебор prefix 1..40 для {GETPLATINUM_ACCOUNT!r}\n")
    found: list[int] = []
    for prefix in range(1, 41):
        ok, msg = try_prefix(prefix)
        mark = "OK" if ok else "—"
        print(f"  prefix={prefix:2d}  {mark}  {msg}")
        if ok:
            found.append(prefix)

    if found:
        print(f"\nРабочие prefix: {found}")
        print(f"Пропишите: GETPLATINUM_POSITION_PREFIX={found[0]}")
        return 0

    print("\nНи один prefix 1..40 не дал formUrl. Напишите support@getplatinum.ru")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())