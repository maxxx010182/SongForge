from backend.services import site_notice


def test_site_notice_off_until_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(site_notice, "NOTICE_PATH", tmp_path / "site_notice.json")
    notice = site_notice.get_notice()
    assert notice["on"] is False
    assert "работы" in notice["title"].lower()

    saved = site_notice.set_notice(
        on=True,
        title="Технические работы",
        text="Подождите немного.",
    )
    assert saved["on"] is True
    loaded = site_notice.get_notice()
    assert loaded["on"] is True
    assert loaded["title"] == "Технические работы"
    assert loaded["text"] == "Подождите немного."

    site_notice.set_notice(on=False, title="", text="")
    off = site_notice.get_notice()
    assert off["on"] is False
    assert off["title"] == site_notice.DEFAULT_TITLE


def test_site_notice_plain_text_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(site_notice, "NOTICE_PATH", tmp_path / "site_notice.json")
    long_title = "А" * 400
    saved = site_notice.set_notice(on=True, title=long_title, text="ок")
    assert len(saved["title"]) == site_notice.TITLE_MAX
