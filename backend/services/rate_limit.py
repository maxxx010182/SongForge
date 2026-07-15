"""In-memory sliding-window rate limit (один процесс PM2 — достаточно для беты)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, limit: int, window_sec: float) -> bool:
        """True — пропустить; False — лимит превышен."""
        if limit <= 0 or window_sec <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            q = self._buckets[key]
            cutoff = now - window_sec
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        """Для тестов."""
        with self._lock:
            self._buckets.clear()


# Глобальный экземпляр приложения
limiter = RateLimiter()
