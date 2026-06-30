from typing import Any, Optional

import requests

from backend.logger import log
from backend.models import ProductionPlan, TrackVariant
from backend.settings import APIPASS_API_KEY, APIPASS_BASE
from backend.utils.text import clean_text


class ApiPassClient:
    def __init__(self) -> None:
        self._headers = {
            "Authorization": f"Bearer {APIPASS_API_KEY}",
            "Content-Type": "application/json",
        }

    def _ensure_key(self) -> None:
        if not APIPASS_API_KEY:
            raise RuntimeError("APIPASS_API_KEY is not configured")

    @staticmethod
    def _vocal_gender(plan: ProductionPlan) -> Optional[str]:
        gender = (plan.vocal_gender or "").strip().lower()
        if gender in {"m", "f"}:
            return gender
        if plan.vocal == "male":
            return "m"
        if plan.vocal == "female":
            return "f"
        return None

    def create_task(
        self,
        *,
        lyrics: str,
        style: str,
        title: str,
        plan: ProductionPlan,
    ) -> str:
        self._ensure_key()

        prompt = "" if plan.instrumental else clean_text(lyrics)

        input_data: dict[str, Any] = {
            "model_version": plan.model_version,
            "customMode": True,
            "instrumental": plan.instrumental,
            "prompt": prompt,
            "style": style,
            "title": title[:75],
            "negativeTags": plan.negative_tags,
            "styleWeight": plan.style_weight,
            "weirdnessConstraint": plan.weirdness_constraint,
            "audioWeight": plan.audio_weight,
        }

        vocal_gender = self._vocal_gender(plan)
        if vocal_gender:
            input_data["vocalGender"] = vocal_gender

        payload = {
            "model": "suno/generate",
            "input": input_data,
            "channel": plan.channel,
        }

        log.info(
            "APIPass createTask: title=%s, style_len=%s, lyrics_len=%s",
            title[:40],
            len(style),
            len(lyrics),
        )

        response = requests.post(
            f"{APIPASS_BASE}/createTask",
            headers=self._headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        task_id = data.get("data", {}).get("taskId")
        if not task_id:
            raise RuntimeError(f"APIPass did not return taskId: {data}")
        log.info("APIPass task created: %s", task_id)
        return task_id

    def get_status(self, task_id: str) -> dict[str, Any]:
        self._ensure_key()

        response = requests.get(
            f"{APIPASS_BASE}/recordInfo",
            headers={"Authorization": f"Bearer {APIPASS_API_KEY}"},
            params={"taskId": task_id},
            timeout=20,
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
            "queue": "Задача в очереди Suno...",
            "generating": "Suno создаёт ваш трек...",
            "success": "Готово!",
            "fail": "Генерация не удалась",
            "failed": "Генерация не удалась",
        }
        return hints.get(state, "Обрабатываем запрос...")