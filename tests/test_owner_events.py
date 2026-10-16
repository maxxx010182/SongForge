"""Список в админке и письмо: нет песни, деньги без нот, ночная копия."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.services import owner_events
from backend.services.payment_service import PaymentService


@contextmanager
def _db(path: Path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _patch_db(monkeypatch, path: Path) -> None:
    @contextmanager
    def connect():
        with _db(path) as conn:
            yield conn

    monkeypatch.setattr(owner_events, "get_connection", connect)


def test_same_case_mails_once(monkeypatch, tmp_path: Path):
    sent: list[str] = []
    _patch_db(monkeypatch, tmp_path / "events.db")
    monkeypatch.setattr(owner_events, "_deliver", lambda text: sent.append(text) or True)

    owner_events.record(owner_events.NO_SONG, owner_events.NO_SONG_TEXT)
    owner_events.record(owner_events.NO_SONG, owner_events.NO_SONG_TEXT)
    owner_events.record(owner_events.NO_SONG, "Музыка не запустилась. Попытку вернули.")

    assert sent == [owner_events.NO_SONG_TEXT]
    rows = owner_events.recent()
    assert len(rows) == 2
    assert all("@" not in row["message"] for row in rows)


def test_address_in_the_text_is_dropped(monkeypatch, tmp_path: Path):
    _patch_db(monkeypatch, tmp_path / "events.db")
    monkeypatch.setattr(owner_events, "_deliver", lambda text: True)
    owner_events.record(owner_events.MONEY, "оплата user@mail.test без нот")
    assert owner_events.recent()[0]["message"] == owner_events.MONEY_TEXT


def test_stale_backup_is_one_row(monkeypatch, tmp_path: Path):
    _patch_db(monkeypatch, tmp_path / "events.db")
    monkeypatch.setattr(owner_events, "_deliver", lambda text: True)
    monkeypatch.setattr(owner_events, "DATA_DIR", tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    (tmp_path / "backup_status.json").write_text(
        json.dumps({"ok": True, "at": old}),
        encoding="utf-8",
    )
    owner_events.watch_backup()
    owner_events.watch_backup()
    rows = owner_events.recent()
    assert len(rows) == 1
    assert rows[0]["kind"] == owner_events.BACKUP


def test_fresh_backup_stays_quiet(monkeypatch, tmp_path: Path):
    _patch_db(monkeypatch, tmp_path / "events.db")
    monkeypatch.setattr(owner_events, "_deliver", lambda text: True)
    monkeypatch.setattr(owner_events, "DATA_DIR", tmp_path)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (tmp_path / "backup_status.json").write_text(
        json.dumps({"ok": True, "at": now}),
        encoding="utf-8",
    )
    owner_events.watch_backup()
    assert owner_events.recent() == []


def test_money_without_a_user_is_not_marked_paid(monkeypatch, tmp_path: Path):
    path = tmp_path / "pay.db"
    noted: list[str] = []

    @contextmanager
    def connect():
        with _db(path) as conn:
            yield conn

    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE payment_orders (
                id TEXT PRIMARY KEY, user_id TEXT, package_id TEXT,
                notes_amount INTEGER, price_rub INTEGER, status TEXT,
                provider TEXT, provider_payment_id TEXT, created_at TEXT, paid_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE TABLE users (id TEXT PRIMARY KEY, balance INTEGER)"
        )
        conn.execute(
            """
            INSERT INTO payment_orders
            VALUES ('order-1', 'missing-user', 'notes_1', 1, 149, 'pending', 'gp', '', '2026-10-16T00:00:00+00:00', NULL)
            """
        )

    monkeypatch.setattr("backend.services.payment_service.get_connection", connect)
    monkeypatch.setattr(
        PaymentService,
        "_note_money_without_notes",
        lambda self: noted.append("gap"),
    )
    result = PaymentService().mark_paid(order_id="order-1", provider_payment_id="pay")
    assert result is None
    assert noted == ["gap"]
    with connect() as conn:
        status = conn.execute(
            "SELECT status FROM payment_orders WHERE id = 'order-1'"
        ).fetchone()["status"]
    assert status == "pending"


def test_mark_paid_adds_the_note(monkeypatch, tmp_path: Path):
    path = tmp_path / "pay-ok.db"
    noted: list[str] = []

    @contextmanager
    def connect():
        with _db(path) as conn:
            yield conn

    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE payment_orders (
                id TEXT PRIMARY KEY, user_id TEXT, package_id TEXT,
                notes_amount INTEGER, price_rub INTEGER, status TEXT,
                provider TEXT, provider_payment_id TEXT, created_at TEXT, paid_at TEXT
            )
            """
        )
        conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY, balance INTEGER)")
        conn.execute("INSERT INTO users VALUES ('user-1', 2)")
        conn.execute(
            """
            INSERT INTO payment_orders
            VALUES ('order-3', 'user-1', 'notes_1', 1, 149, 'pending', 'gp', '', '2026-10-16T00:00:00+00:00', NULL)
            """
        )
    monkeypatch.setattr("backend.services.payment_service.get_connection", connect)
    monkeypatch.setattr(
        PaymentService,
        "_note_money_without_notes",
        lambda self: noted.append("gap"),
    )
    result = PaymentService().mark_paid(order_id="order-3", provider_payment_id="pay")
    assert result is not None
    assert result["notes_added"] == 1
    assert result["balance"] == 3
    assert noted == []
    with connect() as conn:
        status = conn.execute(
            "SELECT status FROM payment_orders WHERE id = 'order-3'"
        ).fetchone()["status"]
    assert status == "paid"


def test_repeated_paid_order_does_not_alert(monkeypatch, tmp_path: Path):
    path = tmp_path / "pay.db"
    noted: list[str] = []

    @contextmanager
    def connect():
        with _db(path) as conn:
            yield conn

    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE payment_orders (
                id TEXT PRIMARY KEY, user_id TEXT, package_id TEXT,
                notes_amount INTEGER, price_rub INTEGER, status TEXT,
                provider TEXT, provider_payment_id TEXT, created_at TEXT, paid_at TEXT
            )
            """
        )
        conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY, balance INTEGER)")
        conn.execute("INSERT INTO users VALUES ('user-1', 3)")
        conn.execute(
            """
            INSERT INTO payment_orders
            VALUES ('order-2', 'user-1', 'notes_1', 1, 149, 'paid', 'gp', 'pay', '2026-10-16T00:00:00+00:00', '2026-10-16T00:01:00+00:00')
            """
        )
    monkeypatch.setattr("backend.services.payment_service.get_connection", connect)
    monkeypatch.setattr(
        PaymentService,
        "_note_money_without_notes",
        lambda self: noted.append("gap"),
    )
    result = PaymentService().mark_paid(order_id="order-2")
    assert result is not None
    assert result["already_paid"] is True
    assert result["notes_added"] == 0
    assert noted == []
