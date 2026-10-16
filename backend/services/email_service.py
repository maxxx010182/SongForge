"""Отправка кодов входа по SMTP (stdlib)."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from backend.logger import log
from backend.settings import (
    ALERT_EMAIL,
    SITE_URL,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
    SMTP_USE_TLS,
)


class EmailService:
    def is_configured(self) -> bool:
        return bool(SMTP_HOST)

    def send_auth_code(self, *, to_email: str, code: str) -> None:
        if not self.is_configured():
            raise RuntimeError("SMTP не настроен")

        sender = SMTP_FROM or SMTP_USER or "noreply@sozdaipesnu.ru"
        msg = EmailMessage()
        msg["Subject"] = "Код входа — СоздайСвоюПесню"
        msg["From"] = sender
        msg["To"] = to_email
        site = SITE_URL.rstrip("/")
        login_url = f"{site}/?auth=email"
        msg.set_content(
            "\n".join(
                [
                    "Ваш код для входа на СоздайСвоюПесню:",
                    "",
                    f"  {code}",
                    "",
                    "Код действует 15 минут.",
                    "",
                    "Вернитесь на сайт и введите код в форме входа:",
                    login_url,
                    "",
                    "Если вы не запрашивали код — просто проигнорируйте это письмо.",
                ]
            )
        )

        self._deliver(msg)

    def send_owner_note(self, text: str) -> bool:
        """Короткое письмо владельцу. False, если почта не настроена или не ушла."""
        if not self.is_configured():
            log.warning("owner note skipped: smtp is off")
            return False
        to = ALERT_EMAIL
        if "@" not in to:
            log.warning("owner note skipped: no address")
            return False
        sender = SMTP_FROM or SMTP_USER or "noreply@sozdaipesnu.ru"
        msg = EmailMessage()
        msg["Subject"] = "СоздайСвоюПесню: нужна проверка"
        msg["From"] = sender
        msg["To"] = to
        msg.set_content(text.strip() + "\n\nОткройте админку сайта.\n")
        try:
            self._deliver(msg)
        except Exception:
            log.warning("owner note was not sent")
            return False
        return True

    def _deliver(self, msg: EmailMessage) -> None:
        try:
            if SMTP_USE_TLS:
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.ehlo()
                    if SMTP_USER:
                        smtp.login(SMTP_USER, SMTP_PASSWORD)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
                    if SMTP_USER:
                        smtp.login(SMTP_USER, SMTP_PASSWORD)
                    smtp.send_message(msg)
        except smtplib.SMTPAuthenticationError as exc:
            log.error(
                "SMTP auth failed host=%s port=%s user=%s: %s",
                SMTP_HOST,
                SMTP_PORT,
                SMTP_USER,
                exc,
            )
            raise RuntimeError(
                "Ошибка входа на почтовый сервер. Проверьте SMTP_USER и SMTP_PASSWORD в .env."
            ) from exc
        except (smtplib.SMTPException, OSError, TimeoutError) as exc:
            log.error(
                "SMTP send failed host=%s port=%s to=%s: %s",
                SMTP_HOST,
                SMTP_PORT,
                msg["To"],
                exc,
            )
            raise RuntimeError(
                "Не удалось отправить письмо. Проверьте SMTP_HOST и порт (587 или 465)."
            ) from exc