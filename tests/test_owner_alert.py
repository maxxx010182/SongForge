"""Повтор одной и той же поломки не шлёт второе сообщение три часа."""

from datetime import datetime, timedelta, timezone

import backend.services.owner_alert as owner_alert


def test_same_break_is_quiet_for_three_hours(monkeypatch, tmp_path):
    monkeypatch.setattr(owner_alert, "_PATH", tmp_path / "owner_alert.json")
    monkeypatch.setattr(owner_alert, "DATA_DIR", tmp_path)
    sent = []
    monkeypatch.setattr(owner_alert, "send_alert", lambda text: sent.append(text) or True)
    assert owner_alert.ping("Музыка не запустилась", fingerprint="music") is True
    assert owner_alert.ping("Музыка не запустилась", fingerprint="music") is False
    assert sent == ["Музыка не запустилась"]


def test_other_break_still_sends(monkeypatch, tmp_path):
    monkeypatch.setattr(owner_alert, "_PATH", tmp_path / "owner_alert.json")
    monkeypatch.setattr(owner_alert, "DATA_DIR", tmp_path)
    sent = []
    monkeypatch.setattr(owner_alert, "send_alert", lambda text: sent.append(text) or True)
    owner_alert.ping("Музыка не запустилась", fingerprint="music")
    assert owner_alert.ping("Песня висит", fingerprint="stuck") is True
    assert sent == ["Музыка не запустилась", "Песня висит"]


def test_old_break_sends_again(monkeypatch, tmp_path):
    monkeypatch.setattr(owner_alert, "_PATH", tmp_path / "owner_alert.json")
    monkeypatch.setattr(owner_alert, "DATA_DIR", tmp_path)
    sent = []
    monkeypatch.setattr(owner_alert, "send_alert", lambda text: sent.append(text) or True)
    old = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
    (tmp_path / "owner_alert.json").write_text(
        '{"sent": {"music": "%s"}}' % old,
        encoding="utf-8",
    )
    assert owner_alert.ping("Музыка не запустилась", fingerprint="music") is True
    assert sent == ["Музыка не запустилась"]


def test_failed_send_does_not_start_the_quiet_period(monkeypatch, tmp_path):
    monkeypatch.setattr(owner_alert, "_PATH", tmp_path / "owner_alert.json")
    monkeypatch.setattr(owner_alert, "DATA_DIR", tmp_path)
    monkeypatch.setattr(owner_alert, "send_alert", lambda text: False)
    assert owner_alert.ping("Музыка не запустилась", fingerprint="music") is False
    monkeypatch.setattr(owner_alert, "send_alert", lambda text: True)
    assert owner_alert.ping("Музыка не запустилась", fingerprint="music") is True
