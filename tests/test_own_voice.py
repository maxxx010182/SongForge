"""Свой голос не меняет обычную песню и не отдаёт номер наружу."""

import json
import struct
import uuid
from pathlib import Path

import pytest

from backend.database.db import get_connection, init_db
from backend.models import ProductionPlan
from backend.services import sunoapi_org_client
from backend.services.music_provider_service import MusicProviderService
from backend.services.suno_input import build_suno_custom_payload
from backend.services.voice_service import VoiceService, audio_kind, voice_id_for_song


def _wav() -> bytes:
    frames = 8000
    pcm = b"\x00\x00" * frames
    header = (
        b"RIFF"
        + struct.pack("<I", 36 + len(pcm))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16)
        + b"data"
        + struct.pack("<I", len(pcm))
    )
    return header + pcm


def _user(trial_used: int) -> dict:
    user_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, balance, created_at, trial_generations_used)
            VALUES (?, ?, ?, 3, datetime('now'), ?)
            """,
            (user_id, f"{user_id}@test.local", user_id, trial_used),
        )
    return {"id": user_id}


def _cleanup(user_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM user_voices WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


class _Storage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def enabled(self) -> bool:
        return True

    def upload_bytes(self, *, key: str, data: bytes, content_type: str) -> str:
        assert key.startswith("voices/")
        assert "user" not in key
        return "https://files.example/" + key

    def delete_key(self, key: str) -> None:
        self.deleted.append(key)


class _Suno:
    def voice_validate(self, *, voice_url: str) -> str:
        assert voice_url.startswith("https://files.example/voices/")
        return "task-validate"

    def voice_validate_info(self, task_id: str) -> dict:
        assert task_id == "task-validate"
        return {"status": "wait_validating", "validateInfo": "Раз два три"}

    def voice_generate(self, *, task_id: str, verify_url: str) -> str:
        assert task_id == "task-validate"
        assert verify_url.startswith("https://files.example/voices/")
        return "task-generate"

    def voice_record_info(self, task_id: str) -> dict:
        assert task_id == "task-generate"
        return {"status": "success", "voiceId": "voice-secret"}


def test_audio_kind_accepts_wav_and_rejects_a_page():
    assert audio_kind(_wav()) == ("audio/wav", "wav")
    assert audio_kind(b"<html>not audio</html>") is None


def test_trial_cannot_save_or_sing():
    init_db()
    user = _user(0)
    service = VoiceService(storage=_Storage(), suno=_Suno())
    try:
        with pytest.raises(ValueError, match="бесплатн"):
            service.save_sample(user, _wav())
        with pytest.raises(ValueError, match="бесплатн"):
            voice_id_for_song(user_id=user["id"], instrumental=False, vocal="female")
    finally:
        _cleanup(user["id"])


def test_save_then_phrase_keeps_the_id_on_the_server():
    init_db()
    user = _user(1)
    service = VoiceService(storage=_Storage(), suno=_Suno())
    from backend.services import voice_service as voice_module

    try:
        first = service.save_sample(user, _wav())
        assert first["status"] == "waiting"
        assert "voice-secret" not in json.dumps(first)
        voice_module._last_poll.clear()
        phrase = service.view(user)
        assert phrase["status"] == "phrase"
        assert phrase["phrase"] == "Раз два три"
        saved = service.save_phrase(user, _wav())
        assert saved["status"] == "saving"
        voice_module._last_poll.clear()
        ready = service.view(user)
        assert ready["status"] == "ready"
        assert "voice-secret" not in json.dumps(ready)
        assert voice_id_for_song(user_id=user["id"], instrumental=False, vocal="auto") == "voice-secret"
        with pytest.raises(ValueError, match="один человек"):
            voice_id_for_song(user_id=user["id"], instrumental=False, vocal="duet")
        with pytest.raises(ValueError, match="без слов"):
            voice_id_for_song(user_id=user["id"], instrumental=True, vocal="female")
    finally:
        _cleanup(user["id"])


def test_shared_payload_has_no_persona_fields():
    plan = ProductionPlan(own_voice_id="secret-voice")
    payload = build_suno_custom_payload(
        lyrics="строка песни",
        style="pop",
        title="Песня",
        plan=plan,
    )
    assert "personaId" not in payload
    assert "personaModel" not in payload


def test_suno_client_adds_persona_only_for_a_saved_voice(monkeypatch):
    monkeypatch.setattr(sunoapi_org_client, "SUNOAPI_ORG_API_KEY", "test-key")
    captured: list[dict] = []

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"code": 200, "data": {"taskId": "song-task"}}

    def _post(url, headers=None, json=None, timeout=None):
        captured.append(json or {})
        return _Response()

    monkeypatch.setattr(sunoapi_org_client.requests, "post", _post)
    client = sunoapi_org_client.SunoApiOrgClient()
    client.create_task(
        lyrics="строка",
        style="pop",
        title="Обычная",
        plan=ProductionPlan(),
    )
    client.create_task(
        lyrics="строка",
        style="pop",
        title="Своим",
        plan=ProductionPlan(own_voice_id="secret-voice"),
    )
    assert "personaId" not in captured[0]
    assert captured[1]["personaId"] == "secret-voice"
    assert captured[1]["personaModel"] == "voice_persona"
    assert captured[0]["prompt"] == captured[1]["prompt"]


def test_voice_song_does_not_ask_the_reserve(monkeypatch):
    from backend.services import music_provider_service as music_module

    monkeypatch.setattr(music_module, "SUNOAPI_ORG_API_KEY", "test-key")
    monkeypatch.setattr(music_module, "APIPASS_API_KEY", "test-key")
    service = MusicProviderService()
    called: list[str] = []
    service._sunoapi.create_task = lambda **kwargs: called.append("suno") or "s1"
    service._apipass.create_task = lambda **kwargs: called.append("api") or "a1"
    ref = service.create_task(
        lyrics="строка",
        style="pop",
        title="Своим",
        plan=ProductionPlan(own_voice_id="secret-voice"),
    )
    assert ref.provider == "sunoapi"
    assert called == ["suno"]

    def _boom(**kwargs):
        raise ValueError("Песня вашим голосом сейчас не запустилась. Ноту вернули.")

    service._sunoapi.create_task = _boom
    with pytest.raises(ValueError):
        service.create_task(
            lyrics="строка",
            style="pop",
            title="Своим",
            plan=ProductionPlan(own_voice_id="secret-voice"),
        )
    assert called == ["suno"]


def test_page_keeps_voice_out_of_the_fast_mode():
    page = Path("index.html").read_text(encoding="utf-8")
    assert 'id="ownVoiceBlock"' in page
    assert "payload.use_own_voice=false" in page
    assert "use_own_voice:wantOwnVoice()" in page
    assert "min-height:44px" in page
