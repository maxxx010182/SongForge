"""Универсальные платежи: заказ в БД + адаптер провайдера (stub / prodamus / …)."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Any

from backend.database.db import get_connection, utc_now
from backend.settings import (
    BETA_DISCOUNT_PERCENT,
    BETA_MANUAL_PAYMENT_ENABLED,
    BETA_PAYMENT_CONTACT,
    BETA_PAYMENT_DETAILS,
    PAYMENT_PROVIDER,
    PRODAMUS_SECRET,
    PRODAMUS_SHOP_ID,
    SITE_URL,
)

PACKAGES: dict[str, dict[str, Any]] = {
    "notes_1": {
        "id": "notes_1",
        "notes": 1,
        "price_rub": 199,
        "label": "Попробовать",
        "discount": "",
    },
    "notes_3": {
        "id": "notes_3",
        "notes": 3,
        "price_rub": 499,
        "label": "Популярный",
        "discount": "−16%",
    },
    "notes_5": {
        "id": "notes_5",
        "notes": 5,
        "price_rub": 799,
        "label": "Творческий",
        "discount": "−20%",
    },
    "notes_10": {
        "id": "notes_10",
        "notes": 10,
        "price_rub": 1199,
        "label": "Продюсер",
        "discount": "−40%",
    },
}


class PaymentService:
    @staticmethod
    def beta_discounted_price(price_rub: int) -> int:
        if not BETA_MANUAL_PAYMENT_ENABLED or BETA_DISCOUNT_PERCENT <= 0:
            return int(price_rub)
        return max(1, int(round(price_rub * (100 - BETA_DISCOUNT_PERCENT) / 100)))

    def beta_config(self) -> dict:
        packages = []
        for pkg in PACKAGES.values():
            full = int(pkg["price_rub"])
            beta = self.beta_discounted_price(full)
            packages.append(
                {
                    **pkg,
                    "price_rub_full": full,
                    "price_rub_beta": beta,
                }
            )
        return {
            "manual_payment": BETA_MANUAL_PAYMENT_ENABLED
            and (PAYMENT_PROVIDER or "stub") == "stub",
            "discount_percent": BETA_DISCOUNT_PERCENT,
            "contact": BETA_PAYMENT_CONTACT,
            "payment_details": BETA_PAYMENT_DETAILS,
            "packages": packages,
        }

    def manual_payment_message(
        self,
        *,
        order_id: str,
        package: dict,
        user_email: str | None,
    ) -> str:
        beta_price = self.beta_discounted_price(int(package["price_rub"]))
        email_hint = (user_email or "").strip() or "ваш email на сайте"
        return (
            f"Бета-акция −{BETA_DISCOUNT_PERCENT}%: {package['notes']} нот за {beta_price}₽ "
            f"(вместо {package['price_rub']}₽).\n\n"
            f"1. Переведите {beta_price}₽: {BETA_PAYMENT_DETAILS}\n"
            f"2. В комментарии к переводу укажите: {order_id}\n"
            f"   или напишите нам: {BETA_PAYMENT_CONTACT}\n"
            f"   (email аккаунта: {email_hint})\n\n"
            f"Ноты начислим вручную после проверки платежа (обычно в течение нескольких часов)."
        )

    def list_packages(self) -> list[dict]:
        return list(PACKAGES.values())

    def create_order(self, *, user_id: str, package_id: str) -> dict:
        package = PACKAGES.get(package_id)
        if not package:
            raise ValueError("Неизвестный пакет")

        order_id = str(uuid.uuid4())
        now = utc_now()
        provider = PAYMENT_PROVIDER or "stub"

        user_email = None
        with get_connection() as conn:
            user_row = conn.execute(
                "SELECT email FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if user_row:
                user_email = user_row["email"]
            conn.execute(
                """
                INSERT INTO payment_orders (
                    id, user_id, package_id, notes_amount, price_rub,
                    status, provider, created_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    order_id,
                    user_id,
                    package_id,
                    package["notes"],
                    package["price_rub"],
                    provider,
                    now,
                ),
            )

        payment_url = self._build_payment_url(
            order_id=order_id,
            user_id=user_id,
            package=package,
            provider=provider,
        )

        message = self._status_message(provider, payment_url)
        if provider == "stub" and BETA_MANUAL_PAYMENT_ENABLED:
            message = self.manual_payment_message(
                order_id=order_id,
                package=package,
                user_email=user_email,
            )

        return {
            "order_id": order_id,
            "status": "pending",
            "package": package,
            "payment_url": payment_url,
            "provider": provider,
            "message": message,
            "beta_price_rub": self.beta_discounted_price(int(package["price_rub"])),
        }

    def get_order(self, *, user_id: str, order_id: str) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM payment_orders WHERE id = ? AND user_id = ?",
                (order_id, user_id),
            ).fetchone()
        if not row:
            raise ValueError("Заказ не найден")
        package = PACKAGES.get(row["package_id"], {})
        return {
            "order_id": row["id"],
            "status": row["status"],
            "package": package,
            "notes_amount": row["notes_amount"],
            "price_rub": row["price_rub"],
            "provider": row["provider"],
            "paid_at": row["paid_at"],
        }

    def mark_paid(
        self,
        *,
        order_id: str,
        provider_payment_id: str | None = None,
    ) -> dict | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM payment_orders WHERE id = ?",
                (order_id,),
            ).fetchone()
            if not row or row["status"] == "paid":
                return None

            conn.execute(
                """
                UPDATE payment_orders
                SET status = 'paid',
                    provider_payment_id = ?,
                    paid_at = ?
                WHERE id = ?
                """,
                (provider_payment_id or "", utc_now(), order_id),
            )
            conn.execute(
                "UPDATE users SET balance = balance + ? WHERE id = ?",
                (int(row["notes_amount"]), row["user_id"]),
            )
            balance_row = conn.execute(
                "SELECT balance FROM users WHERE id = ?",
                (row["user_id"],),
            ).fetchone()

        return {
            "order_id": order_id,
            "user_id": row["user_id"],
            "notes_added": int(row["notes_amount"]),
            "balance": int(balance_row["balance"]) if balance_row else 0,
        }

    def handle_webhook(self, provider: str, payload: dict) -> dict | None:
        if provider == "stub":
            order_id = payload.get("order_id")
            if not order_id:
                raise ValueError("order_id обязателен")
            return self.mark_paid(order_id=order_id, provider_payment_id="stub")

        if provider == "prodamus":
            return self._handle_prodamus_webhook(payload)

        raise ValueError(f"Провайдер {provider} не поддерживается")

    def _build_payment_url(
        self,
        *,
        order_id: str,
        user_id: str,
        package: dict,
        provider: str,
    ) -> str | None:
        if provider == "stub":
            return None
        if provider == "prodamus":
            if not PRODAMUS_SHOP_ID:
                return None
            # Заготовка: финальный URL соберётся после согласования с Продамус
            return (
                f"{SITE_URL}/pay/checkout?order_id={order_id}"
                f"&provider=prodamus&amount={package['price_rub']}"
            )
        return None

    def _handle_prodamus_webhook(self, payload: dict) -> dict | None:
        if not PRODAMUS_SECRET:
            raise ValueError("PRODAMUS_SECRET не настроен")

        signature = payload.pop("signature", "")
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        expected = hmac.new(
            PRODAMUS_SECRET.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Неверная подпись webhook")

        order_id = payload.get("order_id") or payload.get("order_num")
        if not order_id:
            raise ValueError("order_id не найден в webhook")
        if payload.get("payment_status") not in {"success", "paid", "completed"}:
            return None
        return self.mark_paid(
            order_id=str(order_id),
            provider_payment_id=str(payload.get("payment_id", "")),
        )

    @staticmethod
    def _status_message(provider: str, payment_url: str | None) -> str:
        if payment_url:
            return "Перенаправляем на страницу оплаты…"
        if provider == "stub":
            return (
                "Оплата подключается. Заказ создан — после согласования "
                "с платёжной системой оплата откроется автоматически."
            )
        return "Ожидаем настройку платёжного провайдера."