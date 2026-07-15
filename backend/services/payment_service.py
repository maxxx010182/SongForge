"""Универсальные платежи: заказ в БД + адаптер провайдера (getplatinum / stub / …)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import uuid
from typing import Any

import requests

from backend.database.db import get_connection, utc_now
from backend.logger import log
from backend.settings import (
    GETPLATINUM_ACCOUNT,
    GETPLATINUM_API_KEY,
    GETPLATINUM_POSITION_PREFIX,
    GETPLATINUM_VAT,
    PAYMENT_PROVIDER,
    PRODAMUS_SECRET,
    PRODAMUS_SHOP_ID,
    SITE_URL,
)

PACKAGES: dict[str, dict[str, Any]] = {
    "notes_1": {
        "id": "notes_1",
        "notes": 1,
        "price_rub": 299,
        "label": "Попробовать",
        "discount": "",
    },
    "notes_3": {
        "id": "notes_3",
        "notes": 3,
        "price_rub": 749,
        "label": "Популярный",
        "discount": "−16%",
    },
    "notes_5": {
        "id": "notes_5",
        "notes": 5,
        "price_rub": 1199,
        "label": "Творческий",
        "discount": "−20%",
    },
    "notes_10": {
        "id": "notes_10",
        "notes": 10,
        "price_rub": 1799,
        "label": "Продюсер",
        "discount": "−40%",
    },
}


class PaymentService:
    def list_packages(self) -> list[dict]:
        return list(PACKAGES.values())

    def create_order(
        self,
        *,
        user_id: str,
        package_id: str,
        user_email: str = "",
        user_display_name: str = "",
    ) -> dict:
        package = PACKAGES.get(package_id)
        if not package:
            raise ValueError("Неизвестный пакет")

        order_id = str(uuid.uuid4())
        now = utc_now()
        provider = PAYMENT_PROVIDER or "stub"

        with get_connection() as conn:
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
            user_email=user_email,
            user_display_name=user_display_name,
        )

        return {
            "order_id": order_id,
            "status": "pending",
            "package": package,
            "payment_url": payment_url,
            "provider": provider,
            "message": self._status_message(provider, payment_url),
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
        provider = (provider or "").strip().lower()
        active = (PAYMENT_PROVIDER or "stub").strip().lower()

        if provider == "stub":
            if active != "stub":
                raise ValueError("Stub webhook отключён на продакшене")
            order_id = payload.get("order_id")
            if not order_id:
                raise ValueError("order_id обязателен")
            return self.mark_paid(order_id=order_id, provider_payment_id="stub")

        if provider == "prodamus":
            return self._handle_prodamus_webhook(payload)

        if provider == "getplatinum":
            return self._handle_getplatinum_webhook(payload)

        raise ValueError(f"Провайдер {provider} не поддерживается")

    def _build_payment_url(
        self,
        *,
        order_id: str,
        user_id: str,
        package: dict,
        provider: str,
        user_email: str = "",
        user_display_name: str = "",
    ) -> str | None:
        if provider == "stub":
            return None
        if provider == "prodamus":
            if not PRODAMUS_SHOP_ID:
                return None
            return (
                f"{SITE_URL}/pay/checkout?order_id={order_id}"
                f"&provider=prodamus&amount={package['price_rub']}"
            )
        if provider == "getplatinum":
            return self._init_getplatinum_payment(
                order_id=order_id,
                user_id=user_id,
                package=package,
                user_email=user_email,
                user_display_name=user_display_name,
            )
        return None

    def _init_getplatinum_payment(
        self,
        *,
        order_id: str,
        user_id: str,
        package: dict,
        user_email: str,
        user_display_name: str,
    ) -> str | None:
        if not GETPLATINUM_API_KEY or not GETPLATINUM_ACCOUNT:
            log.warning("GetPlatinum: не заданы GETPLATINUM_API_KEY / GETPLATINUM_ACCOUNT")
            return None
        if not GETPLATINUM_POSITION_PREFIX:
            log.warning("GetPlatinum: не задан GETPLATINUM_POSITION_PREFIX в .env")
            return None
        try:
            position_prefix = int(GETPLATINUM_POSITION_PREFIX)
        except ValueError:
            log.error(
                "GetPlatinum: GETPLATINUM_POSITION_PREFIX должен быть числом, got %r",
                GETPLATINUM_POSITION_PREFIX,
            )
            return None

        account = GETPLATINUM_ACCOUNT.strip().lower().removesuffix(".getplatinum.ru")
        url = f"https://{account}.getplatinum.ru/api/public/pay/init-payment-url"
        notes = int(package["notes"])
        # GetPlatinum API: amount и price в копейках (119900 = 1199.00 RUB)
        amount = int(package["price_rub"]) * 100
        position_name = (
            f"Пакет {notes} {'нота' if notes == 1 else 'ноты' if 2 <= notes <= 4 else 'нот'} "
            f"— СоздайСвоюПесню"
        )

        # Для GetPlatinum важно передавать реальные контактные данные,
        # чтобы чеки (через Мой налог) приходили на правильную почту.
        # Платформенный display_name — это ник, а не ФИО.
        # Если email выглядит как фейковый (с .local или внутренним доменом) — не передаём,
        # чтобы в форме GetPlatinum пользователь сам ввёл настоящие данные.
        # Имя тоже не передаём.
        safe_email = ""
        if user_email and "@" in user_email:
            lower_email = user_email.lower()
            if not any(bad in lower_email for bad in (".local", "sozdaipesnu.local", "songforge.local", "test.local", "example.com")):
                safe_email = user_email

        safe_name = ""  # никогда не подставляем ник как ФИО

        payload = {
            "dealId": order_id,
            "currency": "RUB",
            "amount": amount,
            "positions": [
                {
                    "prefix": position_prefix,
                    "name": position_name,
                    "price": amount,
                    "quantity": 1,
                    "vat": GETPLATINUM_VAT,
                }
            ],
            "clientParams": {
                "clientId": user_id,
                "email": safe_email,
                "name": safe_name,
            },
            "notificationUrl": f"{SITE_URL}/api/payment/webhook/getplatinum",
            "successUrl": f"{SITE_URL}/?payment=success&order={order_id}",
            "failUrl": f"{SITE_URL}/?payment=failed",
            "customParams": {"package_id": package["id"], "notes": notes},
        }

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
            log.error("GetPlatinum init-payment-url failed: %s", exc)
            return None

        if response.status_code >= 400:
            log.error(
                "GetPlatinum init-payment-url HTTP %s: %s",
                response.status_code,
                data,
            )
            return None

        error_code = data.get("errorCode")
        if error_code not in (None, 0, "0"):
            log.error("GetPlatinum errorCode=%s: %s", error_code, data)
            return None

        form_url = data.get("formUrl") or data.get("paymentUrl") or data.get("url")
        if not form_url:
            log.error("GetPlatinum: нет formUrl в ответе: %s", data)
            return None
        return str(form_url)

    @staticmethod
    def _strip_checksum_from_raw(raw_body: bytes) -> bytes | None:
        """Убрать поле checksum/signature из JSON-тела, сохранив исходное форматирование."""
        try:
            text = raw_body.decode("utf-8")
        except UnicodeDecodeError:
            return None
        patterns = (
            r',\s*"(checksum|Checksum|signature|sign|hash)"\s*:\s*"[^"]*"',
            r'"(checksum|Checksum|signature|sign|hash)"\s*:\s*"[^"]*"\s*,\s*',
            r'"(checksum|Checksum|signature|sign|hash)"\s*:\s*"[^"]*"',
        )
        for pat in patterns:
            new_text, n = re.subn(pat, "", text, count=1)
            if n:
                return new_text.encode("utf-8")
        return None

    def verify_getplatinum_webhook(self, raw_body: bytes, payload: dict) -> bool:
        """Проверка подписи GetPlatinum webhook.

        Официальный алгоритм в публичной доке размыт; v2.11.19 угадал HMAC «как Prodamus»
        и на реальных webhook'ах начал отдавать 400 → ноты не начислялись.
        Пробуем несколько канонических вариантов (тело без checksum + API key).
        """
        if not GETPLATINUM_API_KEY or not raw_body:
            log.warning("GetPlatinum verify: missing API key or empty body")
            return False

        if not isinstance(payload, dict):
            return False

        checksum = ""
        sig_key = ""
        for key in ("checksum", "Checksum", "signature", "sign", "hash"):
            val = payload.get(key)
            if val:
                checksum = str(val).strip()
                sig_key = key
                break

        if not checksum:
            log.warning(
                "GetPlatinum verify: no checksum field; keys=%s",
                list(payload.keys())[:24],
            )
            return False

        secret = GETPLATINUM_API_KEY.encode("utf-8")
        skip_keys = {sig_key, "checksum", "Checksum", "signature", "sign", "hash"}
        payload_for_sign = {k: v for k, v in payload.items() if k not in skip_keys}

        body_candidates: list[bytes] = []
        # 1) raw body с вырезанным полем подписи (сохраняем пробелы/порядок GP)
        stripped = self._strip_checksum_from_raw(raw_body)
        if stripped:
            body_candidates.append(stripped)
        # 2) пересборка JSON (как пришло / sorted)
        body_candidates.append(
            json.dumps(payload_for_sign, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        body_candidates.append(
            json.dumps(
                payload_for_sign, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
        )
        body_candidates.append(
            json.dumps(payload_for_sign, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
        )
        # 3) весь raw body как есть (на случай если checksum только в заголовке — редко)
        body_candidates.append(raw_body)

        # уникальные тела
        seen: set[bytes] = set()
        unique_bodies: list[bytes] = []
        for b in body_candidates:
            if b and b not in seen:
                seen.add(b)
                unique_bodies.append(b)

        checksum_norm = checksum.strip().removeprefix("sha256=").removeprefix("SHA256=")
        checksum_cmp = checksum_norm.lower()
        for body in unique_bodies:
            digest = hmac.new(secret, body, hashlib.sha256).digest()
            variants = (
                digest.hex(),
                base64.b64encode(digest).decode("ascii"),
                hashlib.sha256(body + secret).hexdigest(),
                hashlib.sha256(secret + body).hexdigest(),
                hashlib.sha256(body).hexdigest(),
                hmac.new(secret, body, hashlib.md5).hexdigest(),
                hashlib.md5(body + secret).hexdigest(),
            )
            for expected in variants:
                if hmac.compare_digest(checksum_cmp, expected.lower()):
                    log.info("GetPlatinum webhook signature OK (len_body=%s)", len(body))
                    return True

        log.warning(
            "GetPlatinum verify FAILED: sig_key=%s checksum_len=%s checksum_prefix=%s "
            "keys=%s isSuccess=%s body_len=%s",
            sig_key,
            len(checksum),
            checksum[:12],
            list(payload.keys())[:20],
            payload.get("isSuccess"),
            len(raw_body),
        )
        # Укороченный raw для следующего разбора алгоритма (без API key)
        try:
            preview = raw_body.decode("utf-8", errors="replace")
            if len(preview) > 1200:
                preview = preview[:1200] + "…"
            log.warning("GetPlatinum webhook raw preview: %s", preview)
        except Exception:
            pass
        return False

    def _handle_getplatinum_webhook(self, payload: dict) -> dict | None:
        if not GETPLATINUM_API_KEY:
            raise ValueError("GETPLATINUM_API_KEY не настроен")

        # Логируем для диагностики (важно при проблемах с начислением)
        # Расширили ключи, чтобы ловить реальный формат GetPlatinum (isSuccess + notificationType)
        status_candidates = {
            k: payload.get(k)
            for k in ["paymentStatus", "status", "payment_status", "isSuccess", "notificationType"]
            if k in payload
        }
        log.info("GetPlatinum webhook received: keys=%s, deal candidates=%s, status candidates=%s, isSuccess=%s, notificationType=%s",
                 list(payload.keys())[:12],
                 [payload.get(k) for k in ["dealId","deal_id","order_id","orderId"] if payload.get(k)],
                 status_candidates,
                 payload.get("isSuccess"),
                 payload.get("notificationType"))

        order_id = (
            payload.get("dealId")
            or payload.get("deal_id")
            or payload.get("order_id")
            or payload.get("orderId")
        )
        if not order_id:
            raise ValueError("dealId не найден в webhook GetPlatinum")

        # Проверяем isSuccess напрямую (основной формат, который присылает GetPlatinum)
        is_success_flag = payload.get("isSuccess")
        if isinstance(is_success_flag, bool):
            is_success = is_success_flag
        elif is_success_flag is not None:
            is_success = str(is_success_flag).lower() in ("true", "1", "yes", "success")
        else:
            is_success = False

        # Запасная проверка по старым полям (на случай других форматов)
        if not is_success:
            status_raw = str(
                payload.get("paymentStatus")
                or payload.get("status")
                or payload.get("payment_status")
                or ""
            ).strip()
            status_lower = status_raw.lower()

            success_indicators = ["success", "paid", "completed", "оплач", "done", "finished"]
            is_success = (
                any(ind in status_lower for ind in success_indicators)
                or "success" in status_lower
                or status_raw in ("paymentStatusSuccess", "Success", "PAID", "Paid")
                or any("success" in str(v).lower() or "paid" in str(v).lower() for v in status_candidates.values())
            )

        if not is_success:
            log.info("GetPlatinum webhook ignored (no success indicator) status=%s order=%s, isSuccess_raw=%s",
                     payload.get("paymentStatus") or payload.get("status") or "", order_id, is_success_flag)
            return None

        payment_id = str(
            payload.get("paymentId")
            or payload.get("payment_id")
            or payload.get("transactionId")
            or ""
        )
        return self.mark_paid(order_id=str(order_id), provider_payment_id=payment_id)

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
    def is_getplatinum_configured() -> bool:
        return bool(GETPLATINUM_API_KEY and GETPLATINUM_ACCOUNT)

    @staticmethod
    def _status_message(provider: str, payment_url: str | None) -> str:
        if payment_url:
            return "Перенаправляем на страницу оплаты…"
        if provider == "getplatinum":
            if not PaymentService.is_getplatinum_configured():
                return (
                    "Оплата GetPlatinum не настроена на сервере. "
                    "Администратору: прописать GETPLATINUM_ACCOUNT и GETPLATINUM_API_KEY "
                    "в .env (см. docs/instrukcii/GETPLATINUM-ENV.txt)."
                )
            if not GETPLATINUM_POSITION_PREFIX:
                return (
                    "Оплата GetPlatinum: в .env не задан GETPLATINUM_POSITION_PREFIX "
                    "(префикс позиции из ЛК GetPlatinum). См. docs/instrukcii/GETPLATINUM-ENV.txt."
                )
            return (
                "Не удалось создать ссылку на оплату GetPlatinum. "
                "Проверьте ключ API, аккаунт и prefix в .env или напишите в поддержку."
            )
        if provider == "stub":
            return (
                "Оплата подключается. Заказ создан — после согласования "
                "с платёжной системой оплата откроется автоматически."
            )
        return "Ожидаем настройку платёжного провайдера."
