import time
from typing import Any

import requests

from backend.logger import log
from backend.models import ProductionPlan, TrackVariant
from backend.services.suno_input import build_suno_custom_payload
from backend.settings import APIPASS_API_KEY, APIPASS_BASE


class ApiPassClient:
    PROVIDER = "apipass"

    def __init__(self) -> None:
        self._headers = {
            "Authorization": f"Bearer {APIPASS_API_KEY}",
            "Content-Type": "application/json",
        }

    def _ensure_key(self) -> None:
        if not APIPASS_API_KEY:
            raise RuntimeError("APIPASS_API_KEY is not configured")

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
        input_data: dict[str, Any] = {
            **fields,
            "model_version": plan.model_version,
        }

        payload = {
            "model": "suno/generate",
            "input": input_data,
            "channel": plan.channel,
        }

        log.info(
            "APIPass createTask: title=%s, vocalGender=%s, "
            "style_len=%s→%s, lyrics_len=%s, neg_len=%s",
            fields["title"][:40],
            input_data.get("vocalGender", "—"),
            len(style),
            len(fields["style"]),
            len(fields["prompt"]),
            len(fields.get("negativeTags", "")),
        )

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = requests.post(
                    f"{APIPASS_BASE}/createTask",
                    headers=self._headers,
                    json=payload,
                    timeout=90,
                )
                response.raise_for_status()
                data = response.json()
                task_id = data.get("data", {}).get("taskId")
                if not task_id:
                    raise RuntimeError(f"APIPass did not return taskId: {data}")
                log.info("APIPass task created: %s", task_id)
                return task_id
            except requests.exceptions.Timeout as exc:
                last_error = exc
                log.warning("APIPass createTask timeout (attempt %s/3)", attempt)
                if attempt < 3:
                    time.sleep(2)
                    continue
            except requests.exceptions.RequestException as exc:
                last_error = exc
                log.warning("APIPass createTask failed (attempt %s/3): %s", attempt, exc)
                if attempt < 3:
                    time.sleep(2)
                    continue
                break

        if last_error:
            raise last_error
        raise RuntimeError("APIPass createTask failed")

    def get_status(self, task_id: str) -> dict[str, Any]:
        self._ensure_key()

        response = requests.get(
            f"{APIPASS_BASE}/recordInfo",
            headers={"Authorization": f"Bearer {APIPASS_API_KEY}"},
            params={"taskId": task_id},
            timeout=45,
        )
        response.raise_for_status()
        inner = response.json().get("data", {})
        state = (inner.get("state") or "unknown").lower()

        result: dict[str, Any] = {
            "state": state,
            "fail_code": inner.get("failCode", ""),
            "fail_msg": inner.get("failMsg", ""),
            "tracks": [],
            "progress_hint": self._progress_hint(state),
        }

        if state == "success":
            songs = (inner.get("resultJson") or {}).get("data", [])
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
                            image_url=song.get("image_url") or song.get("imageUrl") or "",
                            duration=float(song.get("duration") or 0),
                        )
                    )

        return result

    @staticmethod
    def _progress_hint(state: str) -> str:
        hints = {
            "queue": "Задача в очереди...",
            "queuing": "Задача в очереди...",
            "generating": "Создаём твой лучший трек...",
            "success": "Финальная обработка...",
            "fail": "Генерация не удалась",
            "failed": "Генерация не удалась",
        }
        return hints.get(state, "Обрабатываем запрос...")