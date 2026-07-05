"""Telegram-уведомления о бета-заказах."""

from unittest.mock import MagicMock, patch

import pytest

from backend.services.telegram_payment_service import (
    CALLBACK_PREFIX,
    TelegramPaymentNotifier,
)


@pytest.fixture
def notifier():
    payment = MagicMock()
    payment.mark_paid.return_value = {
        "order_id": "order-uuid",
        "user_id": "user-1",
        "notes_added": 3,
        "balance": 5,
    }
    return TelegramPaymentNotifier(payment_service=payment)


@patch("backend.services.telegram_payment_service.TELEGRAM_BOT_TOKEN", "test-token")
@patch(
    "backend.services.telegram_payment_service.TELEGRAM_ADMIN_CHAT_IDS",
    frozenset({"111", "222"}),
)
@patch.object(TelegramPaymentNotifier, "_api")
def test_notify_new_order_sends_to_all_admins(mock_api, notifier):
    notifier.notify_new_order(
        order_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        package_id="notes_3",
        user_email="user@test.ru",
        display_name="Викуся",
        beta_price_rub=249,
    )
    assert mock_api.call_count == 2
    chat_ids = {c[1]["chat_id"] for c in mock_api.call_args_list}
    assert chat_ids == {"111", "222"}
    args, kwargs = mock_api.call_args_list[0]
    assert args[0] == "sendMessage"
    assert "249₽" in kwargs["text"]
    assert "user@test.ru" in kwargs["text"]
    btn = kwargs["reply_markup"]["inline_keyboard"][0][0]
    assert btn["text"] == "✅ Начислить 3 нот"
    assert btn["callback_data"].startswith(CALLBACK_PREFIX)


@patch("backend.services.telegram_payment_service.TELEGRAM_BOT_TOKEN", "")
@patch("backend.services.telegram_payment_service.TELEGRAM_ADMIN_CHAT_IDS", frozenset())
def test_notify_skipped_when_disabled(notifier):
    with patch.object(notifier, "_api") as mock_api:
        notifier.notify_new_order(
            order_id="x",
            package_id="notes_1",
            user_email=None,
            display_name=None,
            beta_price_rub=99,
        )
        mock_api.assert_not_called()


@patch("backend.services.telegram_payment_service.TELEGRAM_BOT_TOKEN", "test-token")
@patch(
    "backend.services.telegram_payment_service.TELEGRAM_ADMIN_CHAT_IDS",
    frozenset({"111"}),
)
@patch.object(TelegramPaymentNotifier, "_answer_callback")
@patch.object(TelegramPaymentNotifier, "_api")
@patch("backend.services.telegram_payment_service.get_connection")
def test_confirm_callback_marks_paid(
    mock_conn, mock_api, mock_answer, notifier
):
    mock_cm = MagicMock()
    mock_conn.return_value.__enter__ = MagicMock(return_value=mock_cm)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)
    mock_cm.execute.return_value.fetchone.return_value = {"id": "admin-1"}

    order_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    update = {
        "callback_query": {
            "id": "cb-1",
            "data": f"{CALLBACK_PREFIX}{order_id}",
            "message": {
                "chat": {"id": 111},
                "message_id": 42,
                "text": "Заказ",
            },
        }
    }

    assert notifier.process_update(update) is True
    notifier._payment.mark_paid.assert_called_once_with(
        order_id=order_id,
        provider_payment_id="telegram:111",
    )
    mock_answer.assert_called_once()
    mock_api.assert_called()


@patch("backend.services.telegram_payment_service.TELEGRAM_BOT_TOKEN", "test-token")
@patch(
    "backend.services.telegram_payment_service.TELEGRAM_ADMIN_CHAT_IDS",
    frozenset({"111"}),
)
@patch.object(TelegramPaymentNotifier, "_answer_callback")
def test_reject_unknown_chat(mock_answer, notifier):
    update = {
        "callback_query": {
            "id": "cb-2",
            "data": f"{CALLBACK_PREFIX}order-id",
            "message": {"chat": {"id": 999}},
        }
    }
    assert notifier.process_update(update) is True
    mock_answer.assert_called_once()
    assert mock_answer.call_args[0][1] == "Нет прав для подтверждения оплат"
    notifier._payment.mark_paid.assert_not_called()