"""Страница открытки есть, в студии ссылки нет, без кредита наружу не ходим."""

from fastapi.testclient import TestClient

from backend.app import app
from backend.services import image_gate

client = TestClient(app)


def test_gate_file_does_not_call_out():
    text = open(image_gate.__file__, encoding="utf-8").read().lower()
    assert "kie" not in text
    assert "creat" not in text
    assert "requests" not in text


def test_otkrytka_page_is_not_indexed():
    response = client.get("/otkrytka")
    assert response.status_code == 200
    html = response.text
    assert html.count("<h1") == 1
    assert "Открытка" in html
    assert "Кредитов открытки нет" in html
    assert 'content="noindex' in html
    assert "/api/otkrytka" in html
    assert "Свои фото в этой пробе не берём." in html


def test_guest_cannot_draw():
    response = client.post("/api/otkrytka", json={"prompt": "мама в саду"})
    assert response.status_code == 401
    assert response.json()["detail"] == image_gate.NEED_LOGIN
    status = client.get("/api/otkrytka")
    assert status.status_code == 200
    body = status.json()
    assert body["open"] is True
    assert body["trial"] is True
    assert body["credits"] == 0
    assert body["cards"] == []


def test_studio_has_no_postcard_link():
    html = client.get("/").text
    assert "/otkrytka" not in html
    assert "otkrytka" not in html
