"""Фоновый опрос ApiPass — не блокирует HTTP API."""

from __future__ import annotations

from backend.logger import log
from backend.models import TrackVariant
from backend.services.music_provider_service import MusicProviderService
from backend.services.cabinet_service import CabinetService
from backend.services.generation_quota_service import GenerationQuotaService
from backend.services.history import HistoryService
from backend.services.job_queue import JobQueue
from backend.services.storage_service import StorageService


class MusicPollService:
    TERMINAL = {"success", "failed", "fail"}

    def __init__(self) -> None:
        self._music = MusicProviderService()
        self._history = HistoryService()
        self._quota = GenerationQuotaService()
        self._cabinet = CabinetService()
        self._storage = StorageService()
        self._queue = JobQueue()

    def list_active_task_ids(self) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []

        for item in self._queue.list_poll_tasks():
            task_id = item["task_id"]
            if task_id and task_id not in seen:
                seen.add(task_id)
                ordered.append(task_id)

        for row in self._history.list_generating_tasks():
            task_id = (row.get("task_id") or "").strip()
            if task_id and task_id not in seen:
                seen.add(task_id)
                ordered.append(task_id)

        return ordered

    def process_task(self, task_id: str) -> str:
        production = self._history.get_by_task(task_id) or {}
        production_id = production.get("id", "")
        row = self._history.get_by_id(production_id) if production_id else None

        if row:
            status = (row.get("status") or "").lower()
            if status == "success" and (row.get("music_url_a") or row.get("music_url_b")):
                self._queue.remove_poll(task_id=task_id)
                return "success"
            if status == "failed":
                self._queue.remove_poll(task_id=task_id)
                return "failed"

        provider = production.get("music_provider") or "apipass"
        try:
            status = self._music.get_status(task_id, provider=provider)
        except Exception:
            log.exception("Music poll failed (%s): %s", provider, task_id)
            return "pending"

        state = (status.get("state") or "unknown").lower()
        progress_hint = status.get("progress_hint") or "Создаём твой лучший трек..."
        self._history.update_progress(task_id=task_id, progress_hint=progress_hint)

        if state == "success" and status.get("tracks"):
            tracks: list[TrackVariant] = []
            for item in status["tracks"]:
                if isinstance(item, TrackVariant):
                    tracks.append(item)
                else:
                    tracks.append(TrackVariant.model_validate(item))
            self._history.update_task_result(
                task_id=task_id,
                status="success",
                tracks=tracks,
                progress_hint=progress_hint,
            )
            if production_id:
                if not self._cabinet.complete_prepaid_generation(production_id):
                    self._cabinet.sync_library_audio_from_generation(production_id)
                self._storage.mirror_generation(production_id)
            self._queue.remove_poll(task_id=task_id)
            return "success"

        if state in {"fail", "failed"}:
            self._history.update_task_result(
                task_id=task_id,
                status="failed",
                tracks=[],
                fail_code=status.get("fail_code", ""),
                fail_msg=status.get("fail_msg", "") or "Не удалось создать трек",
                progress_hint=progress_hint,
            )
            if production_id:
                self._quota.refund_if_charged(
                    production_id=production_id,
                    user_id=production.get("user_id"),
                )
                self._quota.refund_trial_on_failed(production_id=production_id)
            self._queue.remove_poll(task_id=task_id)
            return "failed"

        return "pending"