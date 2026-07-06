"""Очередь фоновых задач через Redis (опционально)."""

from __future__ import annotations

import json

from backend.logger import log
from backend.settings import REDIS_ENABLED, REDIS_URL

POLL_TASKS_KEY = "songforge:poll_tasks"


class JobQueue:
    def __init__(self) -> None:
        self._redis = None
        self._available = False
        if not REDIS_ENABLED:
            return
        try:
            import redis

            self._redis = redis.from_url(REDIS_URL, decode_responses=True)
            self._redis.ping()
            self._available = True
        except Exception as exc:
            log.warning("Redis недоступен (%s) — worker опирается на БД", exc)

    @property
    def available(self) -> bool:
        return self._available

    def ping(self) -> bool:
        if not self._redis:
            return False
        try:
            self._redis.ping()
            return True
        except Exception:
            return False

    def enqueue_poll(
        self,
        *,
        task_id: str,
        production_id: str = "",
        music_provider: str = "apipass",
    ) -> None:
        if not self._available or not task_id:
            return
        payload = json.dumps(
            {
                "task_id": task_id,
                "production_id": production_id,
                "music_provider": music_provider or "apipass",
            },
            ensure_ascii=False,
        )
        self._redis.sadd(POLL_TASKS_KEY, payload)

    def list_poll_tasks(self) -> list[dict]:
        if not self._available:
            return []
        raw = self._redis.smembers(POLL_TASKS_KEY)
        tasks: list[dict] = []
        for item in raw:
            try:
                data = json.loads(item)
            except json.JSONDecodeError:
                data = {"task_id": item, "production_id": ""}
            task_id = (data.get("task_id") or "").strip()
            if task_id:
                tasks.append(
                    {
                        "task_id": task_id,
                        "production_id": (data.get("production_id") or "").strip(),
                        "music_provider": (data.get("music_provider") or "apipass").strip(),
                    }
                )
        return tasks

    def remove_poll(self, *, task_id: str) -> None:
        if not self._available or not task_id:
            return
        for item in self._redis.smembers(POLL_TASKS_KEY):
            try:
                data = json.loads(item)
            except json.JSONDecodeError:
                data = {"task_id": item}
            if data.get("task_id") == task_id:
                self._redis.srem(POLL_TASKS_KEY, item)