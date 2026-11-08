"""Загрузка купленных треков в S3-совместимое хранилище (REG.RU)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests

from backend.database.db import get_connection, utc_now
from backend.logger import log
from backend.services.cabinet_service import CabinetService
from backend.services.history import HistoryService
from backend.settings import (
    S3_ACCESS_KEY,
    S3_BUCKET,
    S3_ENABLED,
    S3_ENDPOINT,
    S3_PUBLIC_BASE,
    S3_REGION,
    S3_SECRET_KEY,
)


MIN_MIRROR_BYTES = 100_000
MIN_COVER_BYTES = 500
MAX_COVER_BYTES = 4_500_000
MAX_COPY_ATTEMPTS = 8
COPY_LOOKBACK_DAYS = 45
_COPY_DELAYS_MIN = (15, 60, 360, 1440, 1440, 1440, 1440, 1440)


def image_kind(data: bytes) -> tuple[str, str] | None:
    """Настоящая картинка, не страница ошибки."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


class CoverCopyResult:
    def __init__(self) -> None:
        self.state = "skip"
        self.saved = 0
        self.already = 0
        self.failed = 0
        self.cleared = 0
        self.empty = 0


class StorageService:
    def __init__(self) -> None:
        self._history = HistoryService()
        self._cabinet = CabinetService()
        self._client = None
        self._silent_cover_hosts: set[str] = set()

    def enabled(self) -> bool:
        return bool(
            S3_ENABLED
            and S3_ENDPOINT
            and S3_ACCESS_KEY
            and S3_SECRET_KEY
            and S3_BUCKET
        )

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.enabled():
            raise RuntimeError("S3 storage is not configured")
        import boto3

        self._client = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            region_name=S3_REGION,
        )
        return self._client

    def public_url(self, key: str) -> str:
        if S3_PUBLIC_BASE:
            return f"{S3_PUBLIC_BASE}/{key.lstrip('/')}"
        base = S3_ENDPOINT.rstrip("/")
        return f"{base}/{S3_BUCKET}/{key.lstrip('/')}"

    def upload_from_url(self, *, key: str, source_url: str) -> str:
        client = self._get_client()
        response = requests.get(source_url, timeout=120)
        response.raise_for_status()
        if len(response.content) < MIN_MIRROR_BYTES:
            raise RuntimeError(
                f"S3 source too small ({len(response.content)} bytes): {source_url}"
            )
        content_type = response.headers.get("Content-Type", "audio/mpeg")
        client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=response.content,
            ContentType=content_type,
        )
        public = self.public_url(key)
        log.info("S3 uploaded: %s (%s bytes)", key, len(response.content))
        return public

    def is_our_storage_url(self, url: str) -> bool:
        raw = (url or "").strip()
        if not raw:
            return False
        if S3_PUBLIC_BASE and (
            raw == S3_PUBLIC_BASE or raw.startswith(S3_PUBLIC_BASE + "/")
        ):
            return True
        parsed = urlparse(raw)
        host = (parsed.netloc or "").lower()
        path = parsed.path or ""
        return "s3.regru.cloud" in host and "/tracks/" in path

    def upload_image_from_url(self, *, key_prefix: str, source_url: str) -> str:
        host = (urlparse(source_url).netloc or "").lower()
        if host and host in self._silent_cover_hosts:
            raise RuntimeError("cover host silent")
        try:
            response = requests.get(
                source_url,
                timeout=12,
                headers={
                    "User-Agent": "SongForgeCoverBot/1.0",
                    "Accept": "image/*,*/*",
                },
            )
            response.raise_for_status()
        except requests.ConnectionError:
            if host:
                self._silent_cover_hosts.add(host)
            raise
        data = response.content or b""
        kind = image_kind(data)
        if kind is None or not (MIN_COVER_BYTES <= len(data) <= MAX_COVER_BYTES):
            raise RuntimeError("cover is not an image")
        content_type, ext = kind
        key = f"{key_prefix}.{ext}"
        client = self._get_client()
        client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        public = self.public_url(key)
        log.info("S3 cover uploaded: %s (%s bytes)", key, len(data))
        return public

    def mirror_generation(self, production_id: str, *, force: bool = False) -> bool:
        if not self.enabled():
            return False

        row = self._history.get_by_id(production_id)
        if not row:
            return False
        if int(row.get("storage_synced") or 0) and not force:
            return True

        pairs = [
            ("a", row.get("music_url_a")),
            ("b", row.get("music_url_b")),
        ]
        uploaded: dict[str, str] = {}
        for variant, source_url in pairs:
            if not source_url:
                continue
            key = f"tracks/{production_id}/{variant}.mp3"
            try:
                uploaded[variant] = self.upload_from_url(
                    key=key,
                    source_url=source_url,
                )
            except Exception:
                log.exception(
                    "S3 mirror failed: production=%s variant=%s",
                    production_id,
                    variant,
                )
                return False

        if not uploaded:
            return False

        if row.get("music_url_a") and "a" not in uploaded:
            log.warning(
                "S3 mirror partial: production=%s variant A missing",
                production_id,
            )
            return False
        if row.get("music_url_b") and "b" not in uploaded:
            log.warning(
                "S3 mirror partial: production=%s variant B missing",
                production_id,
            )
            return False

        url_a = uploaded.get("a")
        url_b = uploaded.get("b")
        self._history.update_music_urls(
            production_id=production_id,
            music_url_a=url_a,
            music_url_b=url_b,
            storage_synced=True,
        )
        self._cabinet.update_library_audio_urls(
            generation_id=production_id,
            url_a=url_a,
            url_b=url_b,
        )
        log.info("S3 mirror complete: %s", production_id)
        return True

    def copy_generation(self, production_id: str, *, respect_schedule: bool = False) -> bool:
        """Забрать файл к нам. Если не вышло, следующая попытка позже, не сразу."""
        if not self.enabled():
            return False
        row = self._history.get_by_id(production_id)
        if not row:
            return False
        if int(row.get("storage_synced") or 0):
            return True
        attempts = int(row.get("storage_attempts") or 0)
        if attempts >= MAX_COPY_ATTEMPTS:
            return False
        nxt = (row.get("storage_next_try") or "").strip()
        if respect_schedule and nxt and nxt > utc_now():
            return False
        ok = self.mirror_generation(production_id)
        if not ok:
            self._schedule_retry(production_id)
        return ok

    def retry_pending_copies(self, *, limit: int = 2) -> int:
        """Догнать песни, у которых первая копия не удалась. За один заход мало."""
        if not self.enabled():
            return 0
        now = utc_now()
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=COPY_LOOKBACK_DAYS)
        ).isoformat()
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id
                FROM generations
                WHERE status = 'success'
                  AND COALESCE(storage_synced, 0) = 0
                  AND COALESCE(storage_attempts, 0) < ?
                  AND (storage_next_try IS NULL OR storage_next_try <= ?)
                  AND created_at >= ?
                  AND (music_url_a IS NOT NULL OR music_url_b IS NOT NULL)
                ORDER BY COALESCE(storage_next_try, created_at) ASC
                LIMIT ?
                """,
                (MAX_COPY_ATTEMPTS, now, cutoff, max(1, limit)),
            ).fetchall()
        saved = 0
        for row in rows:
            if self.copy_generation(row["id"], respect_schedule=True):
                saved += 1
        return saved

    def _schedule_retry(self, production_id: str) -> None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(storage_attempts, 0) AS attempts
                FROM generations
                WHERE id = ?
                """,
                (production_id,),
            ).fetchone()
            if not row:
                return
            attempts = int(row["attempts"]) + 1
            delay = _COPY_DELAYS_MIN[min(attempts - 1, len(_COPY_DELAYS_MIN) - 1)]
            nxt = (datetime.now(timezone.utc) + timedelta(minutes=delay)).isoformat()
            conn.execute(
                """
                UPDATE generations
                SET storage_attempts = ?, storage_next_try = ?
                WHERE id = ?
                """,
                (attempts, nxt, production_id),
            )
        log.info("S3 copy postponed: production=%s attempt=%s", production_id, attempts)

    def copy_covers(
        self,
        production_id: str,
        *,
        respect_schedule: bool = False,
        give_up: bool = False,
    ) -> CoverCopyResult:
        """Забрать обложку к нам. Мёртвый адрес не мешает уже скопированной музыке."""
        result = CoverCopyResult()
        if not self.enabled():
            result.state = "off"
            return result
        safe_id = self._safe_track_id(production_id)
        if not safe_id:
            return result
        row = self._history.get_by_id(safe_id)
        if not row or row.get("status") != "success":
            return result
        if int(row.get("cover_synced") or 0):
            result.state = "ready"
            result.already = self._our_cover_count(row)
            return result
        attempts = int(row.get("cover_attempts") or 0)
        if attempts >= MAX_COPY_ATTEMPTS and not give_up:
            # Адрес не стираем: карточка ещё может открыть чужую картинку.
            self._history.update_image_urls(production_id=safe_id, cover_synced=True)
            result.state = "ready"
            return result
        nxt = (row.get("cover_next_try") or "").strip()
        if respect_schedule and nxt and nxt > utc_now():
            result.state = "wait"
            return result

        saved: dict[str, str] = {}
        for variant, field in (("a", "image_url_a"), ("b", "image_url_b")):
            url = (row.get(field) or "").strip()
            if not url:
                result.empty += 1
                continue
            if self.is_our_storage_url(url):
                result.already += 1
                continue
            try:
                saved[variant] = self.upload_image_from_url(
                    key_prefix=f"tracks/{safe_id}/{variant}-cover",
                    source_url=url,
                )
                result.saved += 1
            except Exception:
                log.info("cover not saved: production=%s variant=%s", safe_id, variant)
                result.failed += 1

        if saved:
            self._history.update_image_urls(
                production_id=safe_id,
                image_url_a=saved.get("a"),
                image_url_b=saved.get("b"),
            )
            self._cabinet.update_library_image_urls(
                generation_id=safe_id,
                url_a=saved.get("a"),
                url_b=saved.get("b"),
            )

        if result.failed and not give_up and attempts + 1 < MAX_COPY_ATTEMPTS:
            self._schedule_cover_retry(safe_id)
            result.state = "failed"
            return result
        if result.failed:
            result.cleared = self._settle_failed_covers(safe_id)
            result.state = "ready"
            return result
        self._history.update_image_urls(production_id=safe_id, cover_synced=True)
        result.state = "ready"
        return result

    def list_cover_song_ids(self) -> list[str]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id
                FROM generations
                WHERE status = 'success'
                  AND COALESCE(cover_synced, 0) = 0
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [row["id"] for row in rows]

    def retry_pending_covers(self, *, limit: int = 2) -> int:
        """Догнать обложки новых песен. За один заход мало."""
        if not self.enabled():
            return 0
        now = utc_now()
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id
                FROM generations
                WHERE status = 'success'
                  AND COALESCE(cover_synced, 0) = 0
                  AND COALESCE(cover_attempts, 0) < ?
                  AND (cover_next_try IS NULL OR cover_next_try <= ?)
                ORDER BY COALESCE(cover_next_try, created_at) ASC
                LIMIT ?
                """,
                (MAX_COPY_ATTEMPTS, now, max(1, limit)),
            ).fetchall()
        saved = 0
        for row in rows:
            result = self.copy_covers(row["id"], respect_schedule=True)
            saved += result.saved
        return saved

    def _our_cover_count(self, row: dict) -> int:
        count = 0
        for field in ("image_url_a", "image_url_b"):
            if self.is_our_storage_url(row.get(field) or ""):
                count += 1
        return count

    def _settle_failed_covers(self, production_id: str) -> int:
        """Остановить повтор, адрес картинки не стирать."""
        row = self._history.get_by_id(production_id)
        if not row:
            return 0
        self._history.update_image_urls(production_id=production_id, cover_synced=True)
        log.info("cover left in place: production=%s", production_id)
        return 0

    def _schedule_cover_retry(self, production_id: str) -> None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(cover_attempts, 0) AS attempts
                FROM generations
                WHERE id = ?
                """,
                (production_id,),
            ).fetchone()
            if not row:
                return
            attempts = int(row["attempts"]) + 1
            delay = _COPY_DELAYS_MIN[min(attempts - 1, len(_COPY_DELAYS_MIN) - 1)]
            nxt = (datetime.now(timezone.utc) + timedelta(minutes=delay)).isoformat()
            conn.execute(
                """
                UPDATE generations
                SET cover_attempts = ?, cover_next_try = ?
                WHERE id = ?
                """,
                (attempts, nxt, production_id),
            )
        log.info("cover copy postponed: production=%s attempt=%s", production_id, attempts)

    @staticmethod
    def _safe_track_id(production_id: str) -> str:
        safe = (production_id or "").strip()
        if not safe or "/" in safe or "\\" in safe or ".." in safe:
            return ""
        return safe

    def delete_generation_mirror(self, production_id: str) -> bool:
        """Снять копии трека с хранилища. True, если хранилище выключено или файлы сняты."""
        if not self.enabled():
            return True
        safe_id = (production_id or "").strip()
        if not safe_id or "/" in safe_id or "\\" in safe_id or ".." in safe_id:
            return False
        try:
            client = self._get_client()
            for variant in ("a", "b"):
                client.delete_object(
                    Bucket=S3_BUCKET,
                    Key=f"tracks/{safe_id}/{variant}.mp3",
                )
                for ext in ("jpg", "png", "webp"):
                    client.delete_object(
                        Bucket=S3_BUCKET,
                        Key=f"tracks/{safe_id}/{variant}-cover.{ext}",
                    )
            log.info("S3 delete complete: %s", safe_id)
            return True
        except Exception:
            log.exception("S3 delete failed: production=%s", safe_id)
            return False