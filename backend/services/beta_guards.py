"""Защита беты: concurrent generations + лимит пробных с одного IP в сутки."""

from __future__ import annotations

from datetime import date

from backend.database.db import get_connection, init_db, utc_now
from backend.logger import log
from backend.settings import (
    MAX_CONCURRENT_GENERATIONS,
    MAX_CONCURRENT_PER_USER,
    MAX_TRIAL_PER_IP_PER_DAY,
)


class BetaGuards:
    def __init__(self) -> None:
        init_db()
        self._ensure_table()

    @staticmethod
    def _ensure_table() -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trial_ip_daily (
                    ip TEXT NOT NULL,
                    day TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (ip, day)
                )
                """
            )

    def assert_slot_available(
        self,
        *,
        count_generating: int,
        count_user_generating: int = 0,
    ) -> None:
        if count_generating >= MAX_CONCURRENT_GENERATIONS:
            raise ValueError(
                "Сейчас много людей создают песни. Подождите 1–2 минуты и попробуйте снова."
            )
        if (
            MAX_CONCURRENT_PER_USER > 0
            and count_user_generating >= MAX_CONCURRENT_PER_USER
        ):
            raise ValueError(
                "У вас уже идёт создание песни. Дождитесь результата или обновите страницу."
            )

    def assert_trial_ip_allowed(self, ip: str) -> None:
        ip = (ip or "").strip()
        if not ip or ip in {"127.0.0.1", "::1", "localhost", "testclient"}:
            return
        day = date.today().isoformat()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT count FROM trial_ip_daily WHERE ip = ? AND day = ?",
                (ip, day),
            ).fetchone()
        used = int(row["count"]) if row else 0
        if used >= MAX_TRIAL_PER_IP_PER_DAY:
            log.warning("trial IP daily limit ip=%s used=%s", ip, used)
            raise ValueError(
                "С этого сети уже использовали несколько пробных генераций сегодня. "
                "Войдите в аккаунт и купите ноты, чтобы продолжить."
            )

    def record_trial_ip(self, ip: str) -> None:
        ip = (ip or "").strip()
        if not ip or ip in {"127.0.0.1", "::1", "localhost", "testclient"}:
            return
        day = date.today().isoformat()
        now = utc_now()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT count FROM trial_ip_daily WHERE ip = ? AND day = ?",
                (ip, day),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE trial_ip_daily SET count = count + 1, updated_at = ? "
                    "WHERE ip = ? AND day = ?",
                    (now, ip, day),
                )
            else:
                conn.execute(
                    "INSERT INTO trial_ip_daily (ip, day, count, updated_at) "
                    "VALUES (?, ?, 1, ?)",
                    (ip, day, now),
                )
