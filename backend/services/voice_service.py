"""Свой голос: одна запись на аккаунт, потом короткая фраза, потом номер.

Когда номер пришёл, наши файлы стираем. Дальше песня идёт по номеру.
Номер наружу не отдаём. Ссылку на запись в журнал не пишем.
Обычная песня этот модуль не вызывает.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.database.db import get_connection, init_db, utc_now
from backend.logger import log
from backend.services.generation_quota_service import GenerationQuotaService
from backend.services.storage_service import StorageService

MIN_AUDIO_BYTES = 1_500
MAX_AUDIO_BYTES = 8_000_000
_BUSY_SEC = 20
_POLL_GAP_SEC = 2.0
VOICE_IDLE_DAYS = 14
_VISIT_GAP = timedelta(hours=1)
_last_poll: dict[str, float] = {}

_FAIL = {"fail", "failed", "processing_validate_fail"}
_PENDING = {"wait_processing", "processing_validate", "pending", "processing", ""}


class VoiceService:
    def __init__(
        self,
        *,
        storage: StorageService | None = None,
        suno: Any | None = None,
        quota: GenerationQuotaService | None = None,
    ) -> None:
        init_db()
        self._storage = storage or StorageService()
        self._suno = suno
        self._quota = quota or GenerationQuotaService()

    def _client(self):
        if self._suno is not None:
            return self._suno
        from backend.services.sunoapi_org_client import SunoApiOrgClient

        return SunoApiOrgClient()

    def view(self, user: dict | None) -> dict[str, Any]:
        if not user or not user.get("id"):
            return _hidden()
        if self._quota.user_trial_remaining(user["id"]) > 0:
            return _hidden()
        self._refresh(user["id"])
        return _public(self._row(user["id"]))

    def note_visit(self, user_id: str) -> None:
        """Заход на сайт продлевает срок голоса. Письма и гости сюда не попадают."""
        if not (user_id or "").strip():
            return
        now = datetime.now(timezone.utc)
        with get_connection() as conn:
            row = conn.execute(
                "SELECT last_seen_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return
            seen = _parse_time(row["last_seen_at"])
            if seen and now - seen < _VISIT_GAP:
                return
            conn.execute(
                "UPDATE users SET last_seen_at = ? WHERE id = ?",
                (now.isoformat(), user_id),
            )

    def delete_saved(self, user: dict) -> dict[str, Any]:
        """Стереть голос этого аккаунта. Уже сделанные песни не трогаем."""
        if not user or not user.get("id"):
            raise ValueError("Войдите в аккаунт, чтобы удалить голос.")
        self._forget(user["id"])
        log.info("voice deleted")
        return _public(None)

    def expire_idle(self) -> int:
        """14 дней без входа: записи и номер голоса стираем. Песни остаются."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=VOICE_IDLE_DAYS)
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT v.user_id, v.updated_at, u.last_seen_at
                FROM user_voices v
                LEFT JOIN users u ON u.id = v.user_id
                """
            ).fetchall()
        removed = 0
        for row in rows:
            seen = _parse_time(row["last_seen_at"]) or _parse_time(row["updated_at"])
            if not seen or seen > cutoff:
                continue
            self._forget(row["user_id"])
            removed += 1
        if removed:
            log.info("idle voices removed: %s", removed)
        return removed

    def _forget(self, user_id: str) -> None:
        row = self._row(user_id)
        if not row:
            return
        for key in (row.get("sample_key"), row.get("phrase_key")):
            raw = (key or "").strip()
            if raw:
                self._storage.delete_key(raw)
        with get_connection() as conn:
            conn.execute("DELETE FROM user_voices WHERE user_id = ?", (user_id,))

    def save_sample(self, user: dict, data: bytes, *, consent: bool = False) -> dict[str, Any]:
        self._require_past_trial(user)
        if not consent:
            raise ValueError(
                "Сначала отметьте согласие: голос только для песен этого аккаунта."
            )
        self._check_audio(data)
        user_id = user["id"]
        self._reject_if_busy(user_id)
        if not self._storage.enabled():
            raise ValueError("Свой голос сейчас недоступен. Попробуйте позже.")
        kind = audio_kind(data)
        assert kind is not None
        content_type, ext = kind
        key = f"voices/{uuid.uuid4().hex}.{ext}"
        try:
            url = self._storage.upload_bytes(
                key=key, data=data, content_type=content_type
            )
        except Exception:
            log.warning("voice storage failed")
            raise ValueError("Свой голос сейчас недоступен. Попробуйте позже.") from None
        try:
            task_id = self._client().voice_validate(voice_url=url)
        except Exception:
            log.warning("voice validate was not accepted")
            self._storage.delete_key(key)
            raise ValueError(_plain_fail("")) from None
        if not task_id:
            self._storage.delete_key(key)
            raise ValueError(_plain_fail(""))
        previous = self._row(user_id)
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_voices (
                    user_id, status, sample_key, phrase_key, validate_task_id,
                    generate_task_id, phrase_text, voice_id, fail_msg,
                    updated_at, created_at, consent_at
                ) VALUES (?, 'validating', ?, '', ?, '', '', ?, '', ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    status = 'validating',
                    sample_key = excluded.sample_key,
                    phrase_key = '',
                    validate_task_id = excluded.validate_task_id,
                    generate_task_id = '',
                    phrase_text = '',
                    voice_id = user_voices.voice_id,
                    fail_msg = '',
                    updated_at = excluded.updated_at,
                    consent_at = excluded.consent_at
                """,
                (
                    user_id,
                    key,
                    task_id,
                    (previous or {}).get("voice_id") or "",
                    now,
                    now,
                    now,
                ),
            )
        if previous and previous.get("sample_key") and previous["sample_key"] != key:
            self._storage.delete_key(previous["sample_key"])
        log.info("voice sample stored bytes=%s", len(data))
        return _public(self._row(user_id))

    def save_phrase(self, user: dict, data: bytes) -> dict[str, Any]:
        self._require_past_trial(user)
        self._check_audio(data)
        user_id = user["id"]
        row = self._row(user_id)
        if not row or row["status"] != "phrase" or not (row["validate_task_id"] or "").strip():
            raise ValueError("Сначала дождитесь короткой фразы и произнесите её.")
        if not (row["phrase_text"] or "").strip():
            raise ValueError("Сначала дождитесь короткой фразы и произнесите её.")
        if not self._storage.enabled():
            raise ValueError("Свой голос сейчас недоступен. Попробуйте позже.")
        kind = audio_kind(data)
        assert kind is not None
        content_type, ext = kind
        key = f"voices/{uuid.uuid4().hex}.{ext}"
        try:
            url = self._storage.upload_bytes(
                key=key, data=data, content_type=content_type
            )
        except Exception:
            log.warning("voice phrase storage failed")
            raise ValueError("Свой голос сейчас недоступен. Попробуйте позже.") from None
        try:
            task_id = self._client().voice_generate(
                task_id=row["validate_task_id"],
                verify_url=url,
            )
        except Exception:
            log.warning("voice generate was not accepted")
            self._storage.delete_key(key)
            raise ValueError(
                "Фраза не подошла. Произнесите или спойте её ещё раз, тем же голосом."
            ) from None
        if not task_id:
            self._storage.delete_key(key)
            raise ValueError(
                "Фраза не подошла. Произнесите или спойте её ещё раз, тем же голосом."
            )
        now = utc_now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE user_voices
                SET status = 'confirming',
                    phrase_key = ?,
                    generate_task_id = ?,
                    fail_msg = '',
                    updated_at = ?
                WHERE user_id = ?
                """,
                (key, task_id, now, user_id),
            )
        old_phrase = (row.get("phrase_key") or "").strip()
        if old_phrase and old_phrase != key:
            self._storage.delete_key(old_phrase)
        log.info("voice phrase stored bytes=%s", len(data))
        return _public(self._row(user_id))

    def _require_past_trial(self, user: dict | None) -> None:
        if not user or not user.get("id"):
            raise ValueError("Войдите в аккаунт, чтобы сохранить голос.")
        if self._quota.user_trial_remaining(user["id"]) > 0:
            raise ValueError("Свой голос откроется после первой бесплатной песни.")

    def _reject_if_busy(self, user_id: str) -> None:
        row = self._row(user_id)
        if not row or row["status"] not in {"validating", "confirming"}:
            return
        if _age_sec(row["updated_at"]) < _BUSY_SEC:
            raise ValueError("Уже проверяем запись. Подождите немного.")

    def _refresh(self, user_id: str) -> None:
        row = self._row(user_id)
        if not row or row["status"] not in {"validating", "confirming"}:
            return
        now = time.monotonic()
        if now - _last_poll.get(user_id, 0.0) < _POLL_GAP_SEC:
            return
        _last_poll[user_id] = now
        try:
            if row["status"] == "validating":
                data = self._client().voice_validate_info(row["validate_task_id"])
                self._apply_validate(user_id, data)
            else:
                data = self._client().voice_record_info(row["generate_task_id"])
                self._apply_record(user_id, data)
        except Exception:
            log.warning("voice status check failed")

    def _apply_validate(self, user_id: str, data: dict) -> None:
        status = str(data.get("status") or "").strip().lower()
        phrase = _phrase_text(data)
        if status in _FAIL:
            self._mark_failed(user_id, _plain_fail(str(data.get("errorMessage") or "")))
            return
        if status == "wait_validating" and phrase:
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE user_voices
                    SET status = 'phrase', phrase_text = ?, fail_msg = '', updated_at = ?
                    WHERE user_id = ?
                    """,
                    (phrase[:400], utc_now(), user_id),
                )
            log.info("voice phrase ready")
            return
        if status == "success":
            voice_id = _voice_id(data)
            if voice_id:
                self._mark_ready(user_id, voice_id)
                return
            if phrase:
                with get_connection() as conn:
                    conn.execute(
                        """
                        UPDATE user_voices
                        SET status = 'phrase', phrase_text = ?, fail_msg = '', updated_at = ?
                        WHERE user_id = ?
                        """,
                        (phrase[:400], utc_now(), user_id),
                    )

    def _apply_record(self, user_id: str, data: dict) -> None:
        status = str(data.get("status") or "").strip().lower()
        voice_id = _voice_id(data)
        if status == "success" and voice_id:
            self._mark_ready(user_id, voice_id)
            return
        if status in _FAIL or (status == "success" and not voice_id):
            self._mark_failed(
                user_id,
                "Фраза не совпала. Произнесите или спойте её ещё раз, тем же голосом.",
            )
            return
        if status not in _PENDING and status != "wait_validating" and not voice_id:
            return

    def _mark_ready(self, user_id: str, voice_id: str) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE user_voices
                SET status = 'ready', voice_id = ?, fail_msg = '', updated_at = ?
                WHERE user_id = ?
                """,
                (voice_id[:120], utc_now(), user_id),
            )
        self._drop_files(user_id)
        log.info("voice ready")

    def _drop_files(self, user_id: str) -> None:
        """Стереть наши файлы. Номер голоса и строку аккаунта не трогаем."""
        row = self._row(user_id)
        if not row:
            return
        for key in (row.get("sample_key"), row.get("phrase_key")):
            raw = (key or "").strip()
            if raw:
                self._storage.delete_key(raw)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE user_voices
                SET sample_key = '', phrase_key = '', phrase_text = ''
                WHERE user_id = ?
                """,
                (user_id,),
            )

    def _mark_failed(self, user_id: str, message: str) -> None:
        row = self._row(user_id)
        if row and (row.get("voice_id") or "").strip():
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE user_voices
                    SET status = 'ready', fail_msg = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (message[:200], utc_now(), user_id),
                )
            self._drop_files(user_id)
            log.info("voice replace failed, previous kept")
            return
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE user_voices
                SET status = 'failed', fail_msg = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (message[:200], utc_now(), user_id),
            )
        self._drop_files(user_id)
        log.info("voice failed")

    def _check_audio(self, data: bytes) -> None:
        if not data or len(data) < MIN_AUDIO_BYTES:
            raise ValueError(
                "Запись короткая. Нужно около 10 секунд чистого голоса, без музыки."
            )
        if len(data) > MAX_AUDIO_BYTES:
            raise ValueError("Файл большой. Запишите около 10 секунд.")
        if audio_kind(data) is None:
            raise ValueError("Нужен звуковой файл. Запишите голос здесь или приложите mp3.")

    def _row(self, user_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM user_voices WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None


def voice_id_for_song(*, user_id: str, instrumental: bool, vocal: str) -> str:
    """Номер только из нашей базы. Пустой пользователь и пробная сюда не проходят."""
    if not (user_id or "").strip():
        raise ValueError("Войдите в аккаунт, чтобы петь своим голосом.")
    quota = GenerationQuotaService()
    if quota.user_trial_remaining(user_id) > 0:
        raise ValueError("Свой голос откроется после первой бесплатной песни.")
    if instrumental:
        raise ValueError("Свой голос не ставится на песню без слов.")
    if (vocal or "").strip().lower() == "duet":
        raise ValueError("Свой голос — это один человек. Для дуэта выключите его.")
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT voice_id FROM user_voices WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    voice_id = str(row["voice_id"]).strip() if row and row["voice_id"] else ""
    if not voice_id:
        raise ValueError("Сначала сохраните голос в расширенном режиме.")
    return voice_id


def audio_kind(data: bytes) -> tuple[str, str] | None:
    if len(data) < 12:
        return None
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "audio/wav", "wav"
    if data.startswith(b"OggS"):
        return "audio/ogg", "ogg"
    if data.startswith(b"fLaC"):
        return "audio/flac", "flac"
    if data.startswith(b"ID3"):
        return "audio/mpeg", "mp3"
    if data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return "audio/mpeg", "mp3"
    if data[4:8] == b"ftyp":
        return "audio/mp4", "m4a"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio/webm", "webm"
    if data.startswith(b"caff"):
        return "audio/x-caf", "caf"
    return None


def _hidden() -> dict[str, Any]:
    return {"show": False, "status": "hidden", "phrase": "", "message": "", "kept": False}


def _public(row: dict | None) -> dict[str, Any]:
    if not row:
        return {"show": True, "status": "empty", "phrase": "", "message": "", "kept": False}
    status = row.get("status") or ""
    mapping = {
        "validating": "waiting",
        "phrase": "phrase",
        "confirming": "saving",
        "ready": "ready",
        "failed": "failed",
    }
    public = mapping.get(status, "empty")
    voice_id = (row.get("voice_id") or "").strip()
    kept = bool(voice_id) and public != "ready"
    phrase = (row.get("phrase_text") or "").strip() if public == "phrase" else ""
    message = ""
    if public in {"failed", "ready"}:
        message = (row.get("fail_msg") or "").strip()
    return {
        "show": True,
        "status": public,
        "phrase": phrase,
        "message": message,
        "kept": kept,
    }


def _parse_time(value: str | None) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _phrase_text(data: dict) -> str:
    for key in ("validateInfo", "validate_info", "phrase"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _voice_id(data: dict) -> str:
    for key in ("voiceId", "voice_id", "personaId"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _plain_fail(raw: str) -> str:
    text = (raw or "").lower()
    if any(word in text for word in ("short", "duration", "length", "too small", "vocal")):
        return "Запись короткая или голос не слышно. Нужно около 10 секунд чистого голоса, без музыки."
    if any(word in text for word in ("match", "verif", "phrase", "valid")):
        return "Фраза не совпала. Произнесите или спойте её ещё раз, тем же голосом."
    return "Голос не сохранился. Попробуйте ещё раз: тихая комната и около 10 секунд вашего голоса."


def _age_sec(stamp: str) -> float:
    if not stamp:
        return 9999
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - moment).total_seconds()
    except Exception:
        return 9999
