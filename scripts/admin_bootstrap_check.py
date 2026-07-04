#!/usr/bin/env python3
"""Проверка доступа в /admin: .env, пользователи, admin_users."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.database.db import get_connection, init_db  # noqa: E402
from backend.settings import ADMIN_BOOTSTRAP_EMAILS, ADMIN_IP_ALLOWLIST  # noqa: E402


def main() -> int:
    init_db()
    print("ADMIN_BOOTSTRAP_EMAILS (как видит Python после загрузки .env):")
    if not ADMIN_BOOTSTRAP_EMAILS:
        print("  (пусто — bootstrap не сработает!)")
    else:
        for e in sorted(ADMIN_BOOTSTRAP_EMAILS):
            print(f"  - {e}")

    print("\nADMIN_IP_ALLOWLIST:")
    if not ADMIN_IP_ALLOWLIST:
        print("  (пусто — IP не ограничен)")
    else:
        for ip in sorted(ADMIN_IP_ALLOWLIST):
            print(f"  - {ip}")

    print("\nПользователи с email из bootstrap:")
    with get_connection() as conn:
        if ADMIN_BOOTSTRAP_EMAILS:
            placeholders = ",".join("?" * len(ADMIN_BOOTSTRAP_EMAILS))
            rows = conn.execute(
                f"""
                SELECT id, email, created_at
                FROM users
                WHERE lower(email) IN ({placeholders})
                ORDER BY created_at
                """,
                tuple(ADMIN_BOOTSTRAP_EMAILS),
            ).fetchall()
        else:
            rows = []

        if not rows:
            print("  (нет — сначала войдите на сайте под этим email)")
        else:
            for r in rows:
                print(f"  user_id={r['id']}  email={r['email']}  created={r['created_at']}")

        print("\nЗаписи admin_users:")
        admins = conn.execute(
            """
            SELECT a.user_id, a.role, a.is_active, u.email, a.last_access_at
            FROM admin_users a
            LEFT JOIN users u ON u.id = a.user_id
            ORDER BY a.created_at
            """
        ).fetchall()
        if not admins:
            print("  (пусто — первый вход на /admin создаст super_admin, если email в bootstrap)")
        else:
            for a in admins:
                active = "active" if a["is_active"] else "INACTIVE"
                print(
                    f"  {a['email'] or a['user_id']}  role={a['role']}  {active}  "
                    f"last={a['last_access_at'] or '—'}"
                )

    print("\nЕсли меняли .env — обязательно: pm2 restart songforge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())