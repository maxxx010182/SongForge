"""Контроль доступа к аудио: превью через прокси, полные URL только после покупки."""

from __future__ import annotations

import re
from urllib.parse import quote

import requests
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

from backend.database.db import get_connection
from backend.settings import PREVIEW_LIMIT_SEC, PREVIEW_MAX_BYTES


class AudioAccessService:
    def owns_generation(
        self,
        row,
        *,
        user_id: str | None,
        guest_id: str | None,
    ) -> bool:
        if not row:
            return False
        owner_id = row["user_id"]
        owner_guest = row["guest_id"]
        if user_id and owner_id and owner_id == user_id:
            return True
        if guest_id and owner_guest and owner_guest == guest_id:
            return True
        return False

    def get_generation_row(self, production_id: str):
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM generations WHERE id = ?",
                (production_id,),
            ).fetchone()

    def assert_access(self, row, *, user_id: str | None, guest_id: str | None) -> None:
        if not self.owns_generation(row, user_id=user_id, guest_id=guest_id):
            raise HTTPException(status_code=403, detail="Нет доступа к этой генерации")

    @staticmethod
    def preview_path(production_id: str, variant: int) -> str:
        return f"/api/audio/preview/{production_id}/{variant}"

    def sanitize_tracks(
        self,
        tracks: list[dict],
        *,
        production_id: str,
        purchased: bool,
        prepaid: bool,
    ) -> list[dict]:
        if purchased or prepaid:
            return tracks
        sanitized: list[dict] = []
        for index, track in enumerate(tracks):
            sanitized.append(
                {
                    "id": track.get("id", ""),
                    "audio_url": "",
                    "preview_url": self.preview_path(production_id, index),
                    "image_url": track.get("image_url", ""),
                    "duration": track.get("duration", 0),
                }
            )
        return sanitized

    def resolve_source_url(self, row, variant: int) -> str:
        if variant == 1:
            url = row["music_url_b"] or row["music_url_a"]
        else:
            url = row["music_url_a"] or row["music_url_b"]
        if not url:
            raise HTTPException(status_code=404, detail="Аудио не найдено")
        return url

    def stream_preview(self, source_url: str) -> StreamingResponse:
        try:
            upstream = requests.get(source_url, stream=True, timeout=60)
            upstream.raise_for_status()
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail="Не удалось загрузить превью",
            ) from exc

        content_type = upstream.headers.get("Content-Type", "audio/mpeg")

        def iter_limited():
            sent = 0
            try:
                for chunk in upstream.iter_content(chunk_size=32_768):
                    if not chunk:
                        continue
                    remaining = PREVIEW_MAX_BYTES - sent
                    if remaining <= 0:
                        break
                    if len(chunk) > remaining:
                        chunk = chunk[:remaining]
                    sent += len(chunk)
                    yield chunk
            finally:
                upstream.close()

        headers = {
            "Accept-Ranges": "none",
            "X-Preview-Limit-Sec": str(PREVIEW_LIMIT_SEC),
        }
        return StreamingResponse(
            iter_limited(),
            media_type=content_type,
            headers=headers,
        )

    @staticmethod
    def _download_filename(title: str) -> str:
        cleaned = re.sub(r"[^\wа-яА-ЯёЁ\s-]", "", title or "").strip()
        return (cleaned or "song") + ".mp3"

    @staticmethod
    def _content_disposition(filename: str) -> str:
        # Starlette encodes headers as latin-1 — only ASCII in filename="
        ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename).strip("._")
        if not ascii_name.lower().endswith(".mp3"):
            ascii_name = f"{ascii_name}.mp3" if ascii_name else "song.mp3"
        if not ascii_name:
            ascii_name = "song.mp3"
        encoded = quote(filename, safe="")
        return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"

    def stream_download(self, source_url: str, *, title: str) -> Response:
        upstream_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
        }
        try:
            upstream = requests.get(
                source_url,
                timeout=120,
                headers=upstream_headers,
            )
            upstream.raise_for_status()
            content = upstream.content
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail="Не удалось загрузить файл с сервера музыки",
            ) from exc

        if not content:
            raise HTTPException(status_code=502, detail="Пустой файл с сервера музыки")

        content_type = upstream.headers.get("Content-Type", "audio/mpeg")
        if not content_type or not content_type.isascii():
            content_type = "audio/mpeg"

        # Только ASCII в заголовке — кириллица в имени задаётся на фронте (blob download)
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": 'attachment; filename="song.mp3"'},
        )