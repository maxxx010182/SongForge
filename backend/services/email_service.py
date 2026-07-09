"""Отправка кодов входа по SMTP (stdlib)."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from backend.logger import log
from backend.settings import (
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
        msg.set_content(
            "\n".join(
                [
                    "Ваш код для входа на СоздайСвоюПесню:",
                    "",
                    f"  {code}",
                    "",
                    "Код действует 15 минут.",
                    "",
                    f"Сайт: {SITE_URL}",
                    "",
                    "Если вы не запрашивали код — просто проигнорируйте это письмо.",
                ]
            )
        )

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
                to_email,
                exc,
            )
            raise RuntimeError(
                "Не удалось отправить письмо. Проверьте SMTP_HOST и порт (587 или 465)."
            ) from exc