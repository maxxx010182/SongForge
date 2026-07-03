"""Smoke-тесты API — без ключей внешних сервисов."""

from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["service"] == "SongForge"
    assert "version" in data


def test_index_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_download_library_requires_login():
    response = client.get("/api/audio/download/library/test-library-id")
    assert response.status_code == 401


def test_me_without_session():
    response = client.get("/api/me")
    assert response.status_code == 200
    data = response.json()
    assert data["logged_in"] is False