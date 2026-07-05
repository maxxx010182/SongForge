from backend.database.db import get_connection, init_db
from backend.services.guest_service import GuestService
from backend.settings import GUEST_GENERATION_LIMIT


class GenerationQuotaService:
    """1 бесплатная пробная генерация на гостя/аккаунт; дальше — только с нотами."""

    def __init__(self) -> None:
        init_db()
        self._guest = GuestService()

    @staticmethod
    def _trial_limit() -> int:
        return GUEST_GENERATION_LIMIT

    def user_trial_used(self, user_id: str) -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT trial_generations_used FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return int(row["trial_generations_used"]) if row else 0

    def user_trial_remaining(self, user_id: str) -> int:
        return max(0, self._trial_limit() - self.user_trial_used(user_id))

    def sync_guest_trial_on_login(self, *, guest_id: str, user_id: str) -> None:
        guest_used = self._guest.get_usage(guest_id)
        if guest_used <= 0:
            return
        with get_connection() as conn:
            row = conn.execute(
                "SELECT trial_generations_used FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return
            merged = max(int(row["trial_generations_used"]), guest_used)
            merged = min(merged, self._trial_limit())
            conn.execute(
                "UPDATE users SET trial_generations_used = ? WHERE id = ?",
                (merged, user_id),
            )

    def resolve_mode(self, *, user: dict | None, guest_id: str) -> str:
        """Возвращает 'trial' или 'paid'. Иначе ValueError с текстом для UI."""
        limit = self._trial_limit()

        if user:
            remaining = self.user_trial_remaining(user["id"])
            if remaining > 0:
                return "trial"
            balance = int(user.get("balance") or 0)
            if balance >= 1:
                return "paid"
            raise ValueError(
                "Пробная генерация уже использована. Купите ноты, чтобы создавать новые песни."
            )

        raise ValueError(
            "Войдите в аккаунт — пробная генерация доступна только после регистрации (1 раз на аккаунт)."
        )

    def consume_on_start(
        self,
        *,
        mode: str,
        user: dict | None,
        guest_id: str,
        production_id: str | None = None,
    ) -> int | None:
        """Списывает пробную попытку или 1 ноту. Возвращает новый баланс (для paid)."""
        if mode == "trial":
            if user:
                used = min(self.user_trial_used(user["id"]) + 1, self._trial_limit())
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE users SET trial_generations_used = ? WHERE id = ?",
                        (used, user["id"]),
                    )
            else:
                self._guest.consume_generation(guest_id)
            return int(user.get("balance") or 0) if user else None

        if not user:
            raise ValueError("Для платной генерации нужен вход в аккаунт")

        user_id = user["id"]
        with get_connection() as conn:
            row = conn.execute(
                "SELECT balance FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not row or int(row["balance"]) < 1:
                raise ValueError("Недостаточно нот на балансе")

            conn.execute(
                "UPDATE users SET balance = balance - 1 WHERE id = ?",
                (user_id,),
            )
            new_row = conn.execute(
                "SELECT balance FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if production_id:
                conn.execute(
                    "UPDATE generations SET note_charged = 1 WHERE id = ?",
                    (production_id,),
                )

        return int(new_row["balance"]) if new_row else 0

    def mark_note_charged(self, production_id: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE generations SET note_charged = 1 WHERE id = ?",
                (production_id,),
            )

    def refund_paid_start(self, *, user_id: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE users SET balance = balance + 1 WHERE id = ?",
                (user_id,),
            )

    def refund_trial_start(self, *, user: dict | None, guest_id: str) -> None:
        """Вернуть пробную попытку, если генерация не стартовала."""
        if user:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT trial_generations_used FROM users WHERE id = ?",
                    (user["id"],),
                ).fetchone()
                if not row:
                    return
                used = max(0, int(row["trial_generations_used"]) - 1)
                conn.execute(
                    "UPDATE users SET trial_generations_used = ? WHERE id = ?",
                    (used, user["id"]),
                )
            return

        with get_connection() as conn:
            row = conn.execute(
                "SELECT generations_used FROM guest_sessions WHERE guest_id = ?",
                (guest_id,),
            ).fetchone()
            if not row:
                return
            used = max(0, int(row["generations_used"]) - 1)
            conn.execute(
                "UPDATE guest_sessions SET generations_used = ? WHERE guest_id = ?",
                (used, guest_id),
            )

    def refund_trial_on_failed(self, *, production_id: str) -> bool:
        """Вернуть пробную попытку, если музыка не создалась."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT user_id, guest_id, note_charged, purchased FROM generations WHERE id = ?",
                (production_id,),
            ).fetchone()
        if not row or row["purchased"] or row["note_charged"]:
            return False

        if row["user_id"]:
            self.refund_trial_start(user={"id": row["user_id"]}, guest_id="")
            return True
        if row["guest_id"]:
            self.refund_trial_start(user=None, guest_id=row["guest_id"])
            return True
        return False

    def refund_if_charged(self, *, production_id: str, user_id: str | None) -> bool:
        if not user_id:
            return False
        with get_connection() as conn:
            row = conn.execute(
                "SELECT note_charged, purchased FROM generations WHERE id = ?",
                (production_id,),
            ).fetchone()
            if not row or not row["note_charged"] or row["purchased"]:
                return False
            conn.execute(
                "UPDATE users SET balance = balance + 1 WHERE id = ?",
                (user_id,),
            )
            conn.execute(
                "UPDATE generations SET note_charged = 0 WHERE id = ?",
                (production_id,),
            )
        return True