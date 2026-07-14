"""Клиент sunoapi.org — запасной/второй канал Suno."""

from __future__ import annotations

import time
from typing import Any

import requests

from backend.logger import log
from backend.models import ProductionPlan, TrackVariant
from backend.services.suno_input import build_suno_custom_payload
from backend.settings import SITE_URL, SUNOAPI_ORG_API_KEY, SUNOAPI_ORG_BASE

_SUCCESS_STATES = {"success"}
_PENDING_STATES = {
    "pending",
    "text_success",
    "first_success",
    "generating",
}
_FAIL_STATES = {
    "create_task_failed",
    "generate_audio_failed",
    "callback_exception",
    "sensitive_word_error",
    "failed",
    "fail",
}


class SunoApiOrgClient:
    PROVIDER = "sunoapi"

    def __init__(self) -> None:
        self._headers = {
            "Authorization": f"Bearer {SUNOAPI_ORG_API_KEY}",
            "Content-Type": "application/json",
        }

    def _ensure_key(self) -> None:
        if not SUNOAPI_ORG_API_KEY:
            raise RuntimeError("SUNOAPI_ORG_API_KEY is not configured")

    @staticmethod
    def _callback_url() -> str:
        return f"{SITE_URL.rstrip('/')}/api/webhooks/sunoapi"

    @staticmethod
    def _normalize_model(model_version: str) -> str:
        version = (model_version or "V5_5").strip().upper().replace(".", "_")
        allowed = {"V4", "V4_5", "V4_5PLUS", "V4_5ALL", "V5", "V5_5"}
        if version in allowed:
            return version
        if version.startswith("V5"):
            return "V5_5"
        return "V5_5"

    def create_task(
        self,
        *,
        lyrics: str,
        style: str,
        title: str,
        plan: ProductionPlan,
    ) -> str:
        self._ensure_key()

        fields = build_suno_custom_payload(
            lyrics=lyrics, style=style, title=title, plan=plan
        )
        payload = {
            **fields,
            "duration": 180,
            "model": self._normalize_model(plan.model_version),
            "callBackUrl": self._callback_url(),
        }
        log.info(f"FULL PAYLOAD: {payload}")

        log.info(
            "sunoapi.org create: title=%s, model=%s, style_len=%s, lyrics_len=%s",
            fields["title"][:40],
            payload["model"],
            len(fields["style"]),
            len(fields["prompt"]),
        )

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = requests.post(
                    f"{SUNOAPI_ORG_BASE}/generate",
                    headers=self._headers,
                    json=payload,
                    timeout=90,
                )
                response.raise_for_status()
                body = response.json()
                if body.get("code") not in (None, 200):
                    raise RuntimeError(
                        f"sunoapi.org error {body.get('code')}: {body.get('msg')}"
                    )
                task_id = (body.get("data") or {}).get("taskId")
                if not task_id:
                    raise RuntimeError(f"sunoapi.org did not return taskId: {body}")
                log.info("sunoapi.org task created: %s", task_id)
                return str(task_id)
            except requests.exceptions.Timeout as exc:
                last_error = exc
                log.warning("sunoapi.org create timeout (attempt %s/3)", attempt)
                if attempt < 3:
                    time.sleep(2)
                    continue
            except requests.exceptions.RequestException as exc:
                last_error = exc
                log.warning("sunoapi.org create failed (attempt %s/3): %s", attempt, exc)
                if attempt < 3:
                    time.sleep(2)
                    continue
                break

        if last_error:
            raise last_error
        raise RuntimeError("sunoapi.org create failed")

    def get_status(self, task_id: str) -> dict[str, Any]:
        self._ensure_key()

        response = requests.get(
            f"{SUNOAPI_ORG_BASE}/generate/record-info",
            headers={"Authorization": f"Bearer {SUNOAPI_ORG_API_KEY}"},
            params={"taskId": task_id},
            timeout=45,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("code") not in (None, 200):
            return {
                "state": "failed",
                "fail_code": str(body.get("code", "")),
                "fail_msg": body.get("msg") or "Ошибка sunoapi.org",
                "tracks": [],
                "progress_hint": "Генерация не удалась",
            }

        inner = body.get("data") or {}
        raw_status = (inner.get("status") or "unknown").lower()
        state = self._map_state(raw_status)

        result: dict[str, Any] = {
            "state": state,
            "fail_code": str(inner.get("errorCode") or ""),
            "fail_msg": inner.get("errorMessage") or "",
            "tracks": [],
            "progress_hint": self._progress_hint(raw_status),
        }

        if state == "success":
            response_block = inner.get("response") or {}
            songs = response_block.get("sunoData") or response_block.get("data") or []
            if isinstance(songs, list):
                for song in songs:
                    if not isinstance(song, dict):
                        continue
                    audio_url = song.get("audio_url") or song.get("audioUrl")
                    if not audio_url:
                        continue
                    result["tracks"].append(
                        TrackVariant(
                            id=str(song.get("id", "")),
                            audio_url=audio_url,
                            image_url=song.get("image_url")
                            or song.get("imageUrl")
                            or "",
                            duration=float(song.get("duration") or 0),
                        )
                    )

        if state == "failed" and not result["fail_msg"]:
            result["fail_msg"] = self._fail_message(raw_status)

        return result

    def get_credits(self) -> float | None:
        self._ensure_key()
        try:
            response = requests.get(
                f"{SUNOAPI_ORG_BASE}/generate/credit",
                headers={"Authorization": f"Bearer {SUNOAPI_ORG_API_KEY}"},
                timeout=20,
            )
            response.raise_for_status()
            body = response.json()
            if body.get("code") in (None, 200):
                return float(body.get("data") or 0)
        except requests.RequestException as exc:
            log.warning("sunoapi.org credits check failed: %s", exc)
        return None

    @staticmethod
    def _map_state(raw_status: str) -> str:
        if raw_status in _SUCCESS_STATES:
            return "success"
        if raw_status in _FAIL_STATES:
            return "failed"
        if raw_status in _PENDING_STATES:
            return "generating"
        return "generating"

    @staticmethod
    def _progress_hint(raw_status: str) -> str:
        hints = {
            "pending": "Задача в очереди...",
            "text_success": "Текст готов, создаём музыку...",
            "first_success": "Первый вариант почти готов...",
            "generating": "Создаём твой лучший трек...",
            "success": "Финальная обработка...",
            "sensitive_word_error": "Контент не прошёл модерацию",
        }
        return hints.get(raw_status, "Обрабатываем запрос...")

    @staticmethod
    def _fail_message(raw_status: str) -> str:
        messages = {
            "sensitive_word_error": "Текст или описание содержит запрещённые слова",
            "create_task_failed": "Не удалось создать задачу генерации",
            "generate_audio_failed": "Не удалось сгенерировать аудио",
            "callback_exception": "Ошибка обработки на стороне сервиса",
        }
        return messages.get(raw_status, "Не удалось создать трек")
