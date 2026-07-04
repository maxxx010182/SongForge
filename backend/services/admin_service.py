"""Админ-панель: роли, права, аудит, bootstrap первого super_admin."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.database.db import get_connection, init_db, utc_now
from backend.settings import ADMIN_BOOTSTRAP_EMAILS, ADMIN_IP_ALLOWLIST

ROLES = (
    "super_admin",
    "admin",
    "support",
    "moderator",
    "finance",
    "readonly",
)

PERMISSIONS: dict[str, frozenset[str]] = {
    "dashboard:read": frozenset(ROLES),
    "users:read": frozenset({"super_admin", "admin", "support", "readonly"}),
    "users:write": frozenset({"super_admin", "admin", "support"}),
    "generations:read": frozenset({"super_admin", "admin", "support", "readonly"}),
    "generations:write": frozenset({"super_admin", "admin", "support"}),
    "payments:read": frozenset({"super_admin", "admin", "finance", "readonly"}),
    "payments:write": frozenset({"super_admin", "finance"}),
    "moderation:write": frozenset({"super_admin", "admin", "moderator"}),
    "admins:manage": frozenset({"super_admin"}),
    "system:read": frozenset({"super_admin", "admin"}),
    "system:write": frozenset({"super_admin"}),
}


class AdminService:
    def __init__(self) -> None:
        init_db()

    @staticmethod
    def check_ip_allowed(client_ip: str) -> None:
        if not ADMIN_IP_ALLOWLIST:
            return
        if client_ip not in ADMIN_IP_ALLOWLIST:
            raise PermissionError("Доступ с этого IP запрещён")

    @staticmethod
    def assert_permission(role: str, permission: str) -> None:
        allowed = PERMISSIONS.get(permission)
        if not allowed or role not in allowed:
            raise PermissionError("Недостаточно прав")

    def _bootstrap_email(self, email: str | None) -> bool:
        if not email or not ADMIN_BOOTSTRAP_EMAILS:
            return False
        return email.strip().lower() in ADMIN_BOOTSTRAP_EMAILS

    def resolve_admin(
        self,
        user: dict,
        *,
        ip: str = "",
    ) -> dict | None:
        self.check_ip_allowed(ip)
        user_id = user["id"]
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, user_id, role, is_active, created_at
                FROM admin_users
                WHERE user_id = ? AND is_active = 1
                """,
                (user_id,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE admin_users SET last_access_at = ? WHERE id = ?",
                    (utc_now(), row["id"]),
                )
                return dict(row)

            if not self._bootstrap_email(user.get("email")):
                return None

            admin_id = str(uuid.uuid4())
            now = utc_now()
            conn.execute(
                """
                INSERT INTO admin_users (id, user_id, role, is_active, invited_by, created_at, last_access_at)
                VALUES (?, ?, 'super_admin', 1, NULL, ?, ?)
                """,
                (admin_id, user_id, now, now),
            )
            self._write_audit(
                conn,
                admin_user_id=admin_id,
                action="bootstrap.super_admin",
                target_type="user",
                target_id=user_id,
                details={"email": user.get("email")},
                ip_address=ip,
            )
            return {
                "id": admin_id,
                "user_id": user_id,
                "role": "super_admin",
                "is_active": 1,
                "created_at": now,
            }

    def list_permissions(self, role: str) -> list[str]:
        return sorted(p for p, roles in PERMISSIONS.items() if role in roles)

    def get_dashboard(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        day_ago = (now - timedelta(days=1)).isoformat()
        week_ago = (now - timedelta(days=7)).isoformat()
        stuck_before = (now - timedelta(minutes=10)).isoformat()

        with get_connection() as conn:
            users_total = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
            users_week = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE created_at >= ?",
                (week_ago,),
            ).fetchone()["c"]
            gen_success = conn.execute(
                "SELECT COUNT(*) AS c FROM generations WHERE status = 'success' AND created_at >= ?",
                (day_ago,),
            ).fetchone()["c"]
            gen_error = conn.execute(
                "SELECT COUNT(*) AS c FROM generations WHERE status = 'error' AND created_at >= ?",
                (day_ago,),
            ).fetchone()["c"]
            gen_stuck = conn.execute(
                """
                SELECT COUNT(*) AS c FROM generations
                WHERE status = 'generating' AND created_at < ?
                """,
                (stuck_before,),
            ).fetchone()["c"]
            gen_generating = conn.execute(
                "SELECT COUNT(*) AS c FROM generations WHERE status = 'generating'",
            ).fetchone()["c"]
            orders_paid = conn.execute(
                """
                SELECT COUNT(*) AS c, COALESCE(SUM(price_rub), 0) AS rub
                FROM payment_orders
                WHERE status = 'paid' AND paid_at >= ?
                """,
                (day_ago,),
            ).fetchone()
            published = conn.execute(
                "SELECT COUNT(*) AS c FROM user_library WHERE published_at IS NOT NULL AND published_at != ''",
            ).fetchone()["c"]

        return {
            "users_total": int(users_total),
            "users_week": int(users_week),
            "generations_24h": {
                "success": int(gen_success),
                "error": int(gen_error),
            },
            "generations_stuck": int(gen_stuck),
            "generations_active": int(gen_generating),
            "orders_paid_24h": {
                "count": int(orders_paid["c"]),
                "rub": int(orders_paid["rub"] or 0),
            },
            "tracks_published": int(published),
            "alerts": self._build_alerts(int(gen_stuck), int(gen_error)),
        }

    @staticmethod
    def _build_alerts(stuck: int, errors_24h: int) -> list[dict[str, str]]:
        alerts: list[dict[str, str]] = []
        if stuck > 0:
            alerts.append(
                {
                    "level": "critical",
                    "message": f"Зависших генераций (>10 мин): {stuck}",
                }
            )
        if errors_24h >= 5:
            alerts.append(
                {
                    "level": "warning",
                    "message": f"Ошибок генерации за 24 ч: {errors_24h}",
                }
            )
        return alerts

    def list_generations(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        limit = max(1, min(limit, 200))
        query = """
            SELECT g.id, g.title, g.status, g.task_id, g.created_at, g.user_id,
                   g.purchased, g.note_charged, g.fail_msg,
                   u.email, u.display_name
            FROM generations g
            LEFT JOIN users u ON u.id = g.user_id
        """
        params: list[Any] = []
        if status:
            query += " WHERE g.status = ?"
            params.append(status)
        query += " ORDER BY g.created_at DESC LIMIT ?"
        params.append(limit)

        with get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def search_users(self, *, q: str, limit: int = 30) -> list[dict]:
        limit = max(1, min(limit, 100))
        term = f"%{q.strip().lower()}%"
        if not q.strip():
            return []
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, email, display_name, balance, created_at, trial_generations_used
                FROM users
                WHERE LOWER(COALESCE(email, '')) LIKE ?
                   OR LOWER(display_name) LIKE ?
                   OR id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (term, term, q.strip(), limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def adjust_balance(
        self,
        *,
        admin_id: str,
        admin_role: str,
        target_user_id: str,
        delta: int,
        reason: str,
        ip: str = "",
    ) -> dict:
        self.assert_permission(admin_role, "users:write")
        if admin_role == "support" and abs(delta) > 20:
            raise ValueError("Support: лимит изменения баланса ±20 нот за раз")
        if not reason.strip():
            raise ValueError("Укажите причину")

        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, email, balance FROM users WHERE id = ?",
                (target_user_id,),
            ).fetchone()
            if not row:
                raise ValueError("Пользователь не найден")
            new_balance = int(row["balance"]) + delta
            if new_balance < 0:
                raise ValueError("Баланс не может быть отрицательным")
            conn.execute(
                "UPDATE users SET balance = ? WHERE id = ?",
                (new_balance, target_user_id),
            )
            self._write_audit(
                conn,
                admin_user_id=admin_id,
                action="users.balance_adjust",
                target_type="user",
                target_id=target_user_id,
                details={
                    "delta": delta,
                    "balance_before": int(row["balance"]),
                    "balance_after": new_balance,
                    "reason": reason.strip(),
                    "email": row["email"],
                },
                ip_address=ip,
            )
        return {"user_id": target_user_id, "balance": new_balance, "delta": delta}

    def grant_admin(
        self,
        *,
        admin_id: str,
        admin_role: str,
        target_email: str,
        role: str,
        ip: str = "",
    ) -> dict:
        self.assert_permission(admin_role, "admins:manage")
        if role not in ROLES:
            raise ValueError("Неизвестная роль")
        if role == "super_admin" and admin_role != "super_admin":
            raise ValueError("Только super_admin может назначать super_admin")

        email = target_email.strip().lower()
        with get_connection() as conn:
            user = conn.execute(
                "SELECT id, email FROM users WHERE LOWER(email) = ?",
                (email,),
            ).fetchone()
            if not user:
                raise ValueError("Пользователь с таким email не найден — сначала войдите на сайте")

            existing = conn.execute(
                "SELECT id, role, is_active FROM admin_users WHERE user_id = ?",
                (user["id"],),
            ).fetchone()
            now = utc_now()
            if existing:
                conn.execute(
                    """
                    UPDATE admin_users
                    SET role = ?, is_active = 1, invited_by = ?, last_access_at = ?
                    WHERE id = ?
                    """,
                    (role, admin_id, now, existing["id"]),
                )
                record_id = existing["id"]
            else:
                record_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO admin_users (id, user_id, role, is_active, invited_by, created_at, last_access_at)
                    VALUES (?, ?, ?, 1, ?, ?, ?)
                    """,
                    (record_id, user["id"], role, admin_id, now, now),
                )

            self._write_audit(
                conn,
                admin_user_id=admin_id,
                action="admins.grant",
                target_type="user",
                target_id=user["id"],
                details={"email": email, "role": role},
                ip_address=ip,
            )

        return {"admin_id": record_id, "user_id": user["id"], "email": email, "role": role}

    def list_admins(self, *, admin_role: str) -> list[dict]:
        self.assert_permission(admin_role, "admins:manage")
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT a.id, a.role, a.is_active, a.created_at, a.last_access_at,
                       u.email, u.display_name
                FROM admin_users a
                JOIN users u ON u.id = a.user_id
                ORDER BY a.created_at
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def list_audit(self, *, admin_role: str, limit: int = 100) -> list[dict]:
        self.assert_permission(admin_role, "system:read")
        limit = max(1, min(limit, 500))
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT l.id, l.action, l.target_type, l.target_id, l.details_json,
                       l.ip_address, l.created_at, u.email AS admin_email
                FROM admin_audit_log l
                JOIN admin_users a ON a.id = l.admin_user_id
                JOIN users u ON u.id = a.user_id
                ORDER BY l.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["details"] = json.loads(item.pop("details_json") or "{}")
            except json.JSONDecodeError:
                item["details"] = {}
            out.append(item)
        return out

    @staticmethod
    def _write_audit(
        conn,
        *,
        admin_user_id: str,
        action: str,
        target_type: str | None,
        target_id: str | None,
        details: dict | None,
        ip_address: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO admin_audit_log (
                id, admin_user_id, action, target_type, target_id,
                details_json, ip_address, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                admin_user_id,
                action,
                target_type,
                target_id,
                json.dumps(details or {}, ensure_ascii=False),
                ip_address,
                utc_now(),
            ),
        )