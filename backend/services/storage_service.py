"""Загрузка купленных треков в S3-совместимое хранилище (REG.RU)."""

from __future__ import annotations

import requests

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


class StorageService:
    def __init__(self) -> None:
        self._history = HistoryService()
        self._cabinet = CabinetService()
        self._client = None

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