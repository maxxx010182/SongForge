"""Фоновый worker: опрос Suno/ApiPass и заливка в S3."""

from __future__ import annotations

import time

from backend.logger import log
from backend.services.music_poll_service import MusicPollService
from backend.settings import WORKER_POLL_INTERVAL_SEC


def run_forever() -> None:
    poll_service = MusicPollService()
    log.info(
        "SongForge worker started (poll interval=%ss)",
        WORKER_POLL_INTERVAL_SEC,
    )
    while True:
        task_ids = poll_service.list_active_task_ids()
        if task_ids:
            log.debug("Polling %s active task(s)", len(task_ids))
        for task_id in task_ids:
            try:
                poll_service.process_task(task_id)
            except Exception:
                log.exception("Worker task failed: %s", task_id)
        time.sleep(WORKER_POLL_INTERVAL_SEC)


if __name__ == "__main__":
    run_forever()