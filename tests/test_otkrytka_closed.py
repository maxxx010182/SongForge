"""Закрытая страница открытки: адрес есть, Кие не вызывается, в студии кнопки нет."""

from fastapi.testclient import TestClient

from backend.app import app
from backend.services import image_gate

client = TestClient(app)


def test_gate_does_not_mention_kie():
    text = open(image_gate.__file__, encoding="utf-8").read().lower()
    assert "kie" not in text
    assert "create_task" not in text
    assert image_gate.status()["open"] is False


def test_otkrytka_page_is_closed_and_not_indexed():
    response = client.get("/otkrytka")
    assert response.status_code == 200
    html = response.text
    assert html.count("<h1") == 1
    assert "Открытка" in html
    assert "Закрыто" in html
    assert 'content="noindex' in html
    assert "/api/otkrytka" in html


def test_otkrytka_post_refuses_without_calling_out():
    response = client.post("/api/otkrytka", json={"prompt": "мама в саду", "model": "nano-banana-2-1"})
    assert response.status_code == 403
    assert response.json()["detail"] == image_gate.CLOSED_DETAIL
    status = client.get("/api/otkrytka")
    assert status.status_code == 200
    assert status.json()["open"] is False


def test_studio_has_no_postcard_link():
    html = client.get("/").text
    assert "/otkrytka" not in html
    assert "otkrytka" not in html
