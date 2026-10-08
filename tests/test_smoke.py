"""Smoke-тесты API — без ключей внешних сервисов."""

import json
from pathlib import Path

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


def test_www_host_redirects_home():
    response = client.get(
        "/?utm_source=landing",
        headers={"host": "www.sozdaipesnu.ru"},
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.headers["location"] == "https://sozdaipesnu.ru/?utm_source=landing"


def test_www_forwarded_host_redirects_post():
    response = client.post(
        "/api/produce",
        headers={"host": "127.0.0.1:8000", "x-forwarded-host": "www.sozdaipesnu.ru"},
        json={"idea": "тест"},
        follow_redirects=False,
    )
    assert response.status_code == 308
    assert response.headers["location"] == "https://sozdaipesnu.ru/api/produce"


def test_apex_host_stays():
    response = client.get("/", headers={"host": "sozdaipesnu.ru"})
    assert response.status_code == 200


def test_homepage_seo_marks():
    html = client.get("/").text
    assert html.count("<h1") == 1
    start = html.index('<div id="faqList">')
    end = html.index('<div id="section-support"')
    block = html[start:end]
    assert block.count('class="faq-item"') == 18
    assert "Как работает сервис?" in block
    assert "149₽" in block
    assert "ТВОЯ ПЕСНЯ" in html
    payload = html.split('<script type="application/ld+json">', 1)[1].split("</script>", 1)[0]
    data = json.loads(payload)
    types = [node["@type"] for node in data["@graph"]]
    assert types == ["Organization", "WebSite", "Service"]
    assert data["@graph"][2]["offers"]["price"] == "149"


def test_legal_pages_have_canonical():
    expected = {
        "/legal/terms": "Пользовательское соглашение сервиса СоздайСвоюПесню",
        "/legal/privacy": "Политика конфиденциальности сервиса СоздайСвоюПесню",
        "/legal/offer": "Публичная оферта сервиса СоздайСвоюПесню",
    }
    for path, description in expected.items():
        response = client.get(path)
        assert response.status_code == 200
        assert f'<link rel="canonical" href="https://sozdaipesnu.ru{path}">' in response.text
        assert description in response.text
        assert response.text.count("<h1") == 1


def test_landing_seo_marks():
    html = (Path(__file__).resolve().parents[1] / "landing" / "index.html").read_text(encoding="utf-8")
    assert html.count("<h1") == 1
    payload = html.split('<script type="application/ld+json">', 1)[1].split("</script>", 1)[0]
    data = json.loads(payload)
    assert data["@graph"][0]["name"] == "СоздайСвоюПесню"
    assert data["@graph"][1]["url"] == "https://podarok.sozdaipesnu.ru/"


def test_yandex_webmaster_file():
    response = client.get("/yandex_1c8e66e473ae4245.html")
    assert response.status_code == 200
    assert "Verification: 1c8e66e473ae4245" in response.text


def test_download_library_requires_login():
    response = client.get("/api/audio/download/library/test-library-id")
    assert response.status_code == 401


def test_library_listen_requires_login():
    response = client.get("/api/library/test-library-id/listen")
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
    by_id = {p["id"]: p for p in data}
    assert by_id["notes_1"]["price_rub"] == 149
    assert by_id["notes_3"]["price_rub"] == 375
    assert by_id["notes_5"]["price_rub"] == 599
    assert by_id["notes_10"]["price_rub"] == 899


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


def test_create_payment_order_requires_login():
    response = client.post(
        "/api/payment/create-order",
        json={"package_id": "notes_1"},
    )
    assert response.status_code == 401


def test_create_payment_order_validation_error():
    response = client.post(
        "/api/payment/create-order",
        json={"package_id": {}},
    )
    assert response.status_code == 422


def test_admin_list_generations_includes_audio_urls():
    from backend.services.admin_service import AdminService
    rows = AdminService().list_generations(limit=5)
    assert isinstance(rows, list)
    for r in rows:
        assert "music_url_a" in r
        assert "music_url_b" in r