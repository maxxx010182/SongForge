"""Фоновый опрос ApiPass — не блокирует HTTP API."""

from __future__ import annotations

import json

from backend.logger import log
from backend.models import ProductionPlan, TrackVariant
from backend.services.music_provider_service import MusicProviderService
from backend.services.cabinet_service import CabinetService
from backend.services.generation_quota_service import GenerationQuotaService
from backend.services.history import HistoryService
from backend.services.job_queue import JobQueue
from backend.services.storage_service import StorageService
from backend import settings as sf_settings


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
        active_task = (production.get("task_id") or task_id).strip() or task_id
        try:
            status = self._music.get_status(active_task, provider=provider)
        except Exception:
            log.exception("Music poll failed (%s): %s", provider, active_task)
            return "pending"

        state = (status.get("state") or "unknown").lower()
        progress_hint = status.get("progress_hint") or "Создаём твой лучший трек..."
        self._history.update_progress(task_id=active_task, progress_hint=progress_hint)

        if state == "success" and status.get("tracks"):
            tracks: list[TrackVariant] = []
            for item in status["tracks"]:
                if isinstance(item, TrackVariant):
                    tracks.append(item)
                else:
                    tracks.append(TrackVariant.model_validate(item))
            self._history.update_task_result(
                task_id=active_task,
                status="success",
                tracks=tracks,
                progress_hint=progress_hint,
            )
            if production_id:
                self._storage.copy_generation(production_id)
                if not self._cabinet.complete_prepaid_generation(production_id):
                    self._cabinet.sync_library_audio_from_generation(production_id)
                user_id = (production.get("user_id") or "").strip()
                if user_id:
                    try:
                        from backend.services.messenger_service import MessengerService

                        MessengerService().on_generation_ready(
                            user_id=user_id,
                            generation_id=production_id,
                        )
                    except Exception:
                        log.exception("MAX ready followup failed for %s", production_id)
            self._queue.remove_poll(task_id=task_id)
            if active_task != task_id:
                self._queue.remove_poll(task_id=active_task)
            return "success"

        if state in {"fail", "failed"}:
            if self._handoff_to_apipass(production, active_task):
                return "pending"
            self._history.update_task_result(
                task_id=active_task,
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
            if active_task != task_id:
                self._queue.remove_poll(task_id=active_task)
            return "failed"

        return "pending"

    def _handoff_to_apipass(self, production: dict, failed_task_id: str) -> bool:
        """Suno принял задачу и сломался — один раз та же песня через ApiPass."""
        mode = (sf_settings.MUSIC_PROVIDER or "").strip().lower()
        if mode not in {"fallback_suno", "fallback"}:
            return False
        if not (sf_settings.APIPASS_API_KEY or "").strip():
            return False
        provider = (production.get("music_provider") or "").strip().lower()
        if provider != "sunoapi":
            return False
        production_id = (production.get("id") or "").strip()
        if not production_id:
            return False
        if int(production.get("music_fallback") or 0):
            row = self._history.get_by_id(production_id) or {}
            status = (row.get("status") or "").lower()
            return status != "failed"

        if not self._history.claim_music_fallback(production_id):
            row = self._history.get_by_id(production_id) or {}
            status = (row.get("status") or "").lower()
            return status != "failed"

        title = (production.get("title") or "Моя песня").strip() or "Моя песня"
        lyrics = production.get("lyrics") or ""
        style = production.get("style") or ""
        try:
            plan = ProductionPlan.model_validate(
                json.loads(production.get("plan_json") or "{}")
            )
        except Exception:
            plan = ProductionPlan()

        try:
            new_id = self._music.create_on(
                "apipass",
                lyrics=lyrics,
                style=style,
                title=title,
                plan=plan,
            )
        except Exception:
            log.exception(
                "ApiPass reserve failed after sunoapi task %s",
                failed_task_id,
            )
            return False

        self._history.switch_to_reserve_task(
            production_id=production_id,
            old_task_id=failed_task_id,
            new_task_id=str(new_id),
            music_provider="apipass",
        )
        self._queue.remove_poll(task_id=failed_task_id)
        self._queue.enqueue_poll(
            task_id=str(new_id),
            production_id=production_id,
            music_provider="apipass",
        )
        log.warning(
            "Music provider fallback: apipass after sunoapi fail %s -> %s",
            failed_task_id,
            new_id,
        )
        return True