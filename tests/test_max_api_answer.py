from backend.services.max_api import MaxApi


class _Resp:
    status_code = 200
    content = b"{}"
    text = "{}"

    def json(self):
        return {"success": True}


def test_button_ack_is_a_space_not_an_empty_letter(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        captured["params"] = kwargs.get("params")
        return _Resp()

    monkeypatch.setattr("backend.services.max_api.requests.request", fake_request)
    api = MaxApi(token="test-token")
    assert api.answer_callback("cb-1") is True
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/answers")
    assert captured["params"]["callback_id"] == "cb-1"
    assert captured["json"] == {"notification": " "}


def test_button_ack_keeps_a_real_notice(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _Resp()

    monkeypatch.setattr("backend.services.max_api.requests.request", fake_request)
    api = MaxApi(token="test-token")
    assert api.answer_callback("cb-2", notification="  Готово  ") is True
    assert captured["json"] == {"notification": "Готово"}


def test_button_ack_skips_a_missing_id(monkeypatch):
    called = {"n": 0}

    def fake_request(*args, **kwargs):
        called["n"] += 1
        return _Resp()

    monkeypatch.setattr("backend.services.max_api.requests.request", fake_request)
    api = MaxApi(token="test-token")
    assert api.answer_callback("") is False
    assert called["n"] == 0
