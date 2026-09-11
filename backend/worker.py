"""Фоновый worker: опрос Suno/ApiPass и заливка в S3."""

from __future__ import annotations

import time

from backend.logger import log
from backend.services.max_bot import MaxBot
from backend.services.music_poll_service import MusicPollService
from backend.settings import WORKER_POLL_INTERVAL_SEC

NUDGE_EVERY_SEC = 30


def run_forever() -> None:
    poll_service = MusicPollService()
    max_bot = MaxBot()
    last_nudge = 0.0
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
        now = time.time()
        if now - last_nudge >= NUDGE_EVERY_SEC:
            last_nudge = now
            try:
                sent = max_bot.process_due_nudges()
                extra = max_bot.process_due_followups()
                if sent or extra:
                    log.info("MAX nudges sent: %s followups: %s", sent, extra)
            except Exception:
                log.exception("MAX nudge pass failed")
        time.sleep(WORKER_POLL_INTERVAL_SEC)


if __name__ == "__main__":
    run_forever()