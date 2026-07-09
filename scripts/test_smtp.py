#!/usr/bin/env python3
"""Проверка SMTP из .env на сервере. Запуск: ./venv/bin/python scripts/test_smtp.py"""

from __future__ import annotations

import smtplib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.settings import (  # noqa: E402
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
    SMTP_USE_TLS,
)


def try_connect(host: str, port: int, use_tls: bool) -> str:
    if use_tls:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            if SMTP_USER:
                smtp.login(SMTP_USER, SMTP_PASSWORD)
        return "ok"
    with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
        if SMTP_USER:
            smtp.login(SMTP_USER, SMTP_PASSWORD)
    return "ok"


def main() -> int:
    print("SMTP из .env:")
    print(f"  HOST={SMTP_HOST!r} PORT={SMTP_PORT} USER={SMTP_USER!r} TLS={SMTP_USE_TLS}")
    print(f"  FROM={SMTP_FROM!r} PASSWORD={'set' if SMTP_PASSWORD else 'EMPTY'}")

    if not SMTP_HOST:
        print("FAIL: SMTP_HOST пустой")
        return 1

    try:
        try_connect(SMTP_HOST, SMTP_PORT, SMTP_USE_TLS)
        print(f"OK: login на {SMTP_HOST}:{SMTP_PORT} (TLS={SMTP_USE_TLS})")
        return 0
    except Exception as exc:
        print(f"FAIL текущие настройки: {exc}")

    fallbacks = [
        ("mail.hosting.reg.ru", 587, True),
        ("sm42.hosting.reg.ru", 587, True),
        ("mail.hosting.reg.ru", 465, False),
        ("sm42.hosting.reg.ru", 465, False),
    ]
    print("\nПробуем запасные варианты REG.RU (только connect+login):")
    for host, port, tls in fallbacks:
        if host == SMTP_HOST and port == SMTP_PORT and tls == SMTP_USE_TLS:
            continue
        try:
            try_connect(host, port, tls)
            print(f"  OK  {host}:{port} TLS={tls}  -> пропишите в .env")
        except Exception as exc2:
            print(f"  fail {host}:{port} TLS={tls}: {exc2}")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())