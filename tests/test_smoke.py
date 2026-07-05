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
    assert data["guest_remaining"] == 0


def test_create_song_requires_login():
    response = client.post(
        "/api/create-song",
        json={"idea": "Тестовая песня про закат"},
    )
    assert response.status_code == 403
    assert "аккаунт" in response.json().get("detail", "").lower()


def test_produce_requires_login():
    response = client.post(
        "/api/produce",
        json={"idea": "Тестовая песня про закат"},
    )
    assert response.status_code == 403
    assert "аккаунт" in response.json().get("detail", "").lower()


def test_generate_lyrics_requires_login():
    response = client.post(
        "/api/generate-lyrics",
        json={
            "prompt": "Тестовая песня про закат",
            "genre": "pop",
            "mood": "uplifting",
        },
    )
    assert response.status_code == 403
    assert "аккаунт" in response.json().get("detail", "").lower()


def test_consultant_available_without_legacy_flag():
    response = client.post(
        "/api/consultant/chat",
        json={"message": "Сколько стоят ноты?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("reply")
    assert "временно недоступен" not in data["reply"].lower()
    assert data["success"] is True


def test_explore_public():
    response = client.get("/api/explore")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_payment_packages():
    response = client.get("/api/payment/packages")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "price_rub" in data[0]


def test_explore_listen_not_found():
    response = client.get("/api/explore/nonexistent-id/listen")
    assert response.status_code == 404


def test_public_track_not_found():
    response = client.get("/api/explore/nonexistent-id/public")
    assert response.status_code == 404


def test_track_short_link_not_found():
    response = client.get("/t/nonexistent-id", follow_redirects=False)
    assert response.status_code == 404


def test_explore_like_requires_login():
    response = client.post("/api/explore/nonexistent-id/like")
    assert response.status_code == 401


def test_explore_unlike_requires_login():
    response = client.delete("/api/explore/nonexistent-id/like")
    assert response.status_code == 401


def test_explore_comments_requires_login():
    response = client.post(
        "/api/explore/nonexistent-id/comments",
        json={"text": "Тестовый комментарий"},
    )
    assert response.status_code == 401


def test_explore_comments_list_not_found():
    response = client.get("/api/explore/nonexistent-id/comments")
    assert response.status_code == 400