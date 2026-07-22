"""Карточка 1200x630 для превью ссылки (Telegram / WhatsApp / VK)."""

from __future__ import annotations

import io
import re
import time
from pathlib import Path

import requests

from backend.logger import log

_OG_W = 1200
_OG_H = 630
_OG_CACHE_TTL_SEC = 86400
_SAFE_ID = re.compile(r"^[a-fA-F0-9-]{8,64}$")


def _fetch_bytes(url: str) -> bytes | None:
    if not url:
        return None
    try:
        resp = requests.get(
            url,
            timeout=12,
            headers={
                "User-Agent": "SongForgeCoverBot/1.0",
                "Accept": "image/*,*/*",
            },
        )
        if resp.status_code >= 400 or not resp.content:
            return None
        if len(resp.content) > 4_500_000:
            return None
        return resp.content
    except requests.RequestException as exc:
        log.warning("og image fetch failed: %s", exc)
        return None


def build_og_jpeg(
    *,
    cover_url: str,
    fallback_path: Path | None = None,
) -> bytes:
    """Собрать JPEG 1200×630: тёмный фон + обложка по центру."""
    from PIL import Image, ImageDraw

    bg = Image.new("RGB", (_OG_W, _OG_H), (9, 9, 11))
    draw = ImageDraw.Draw(bg)
    # лёгкое золотое свечение сверху
    for i, alpha in enumerate((28, 18, 10, 5)):
        y0 = i * 40
        draw.rectangle(
            (0, y0, _OG_W, y0 + 80),
            fill=(min(234, 9 + alpha * 4), min(179, 9 + alpha * 3), 8 + alpha),
        )

    cover_bytes = _fetch_bytes(cover_url)
    cover_im = None
    if cover_bytes:
        try:
            cover_im = Image.open(io.BytesIO(cover_bytes)).convert("RGB")
        except Exception as exc:
            log.warning("og cover open failed: %s", exc)
            cover_im = None
    if cover_im is None and fallback_path and fallback_path.is_file():
        try:
            cover_im = Image.open(fallback_path).convert("RGB")
        except Exception:
            cover_im = None

    if cover_im is not None:
        # квадрат ~480px по центру
        side = 480
        cover_im = cover_im.copy()
        cover_im.thumbnail((side, side), Image.Resampling.LANCZOS)
        # скруглённая «рамка» — простая подложка
        pad = 10
        frame_w = cover_im.width + pad * 2
        frame_h = cover_im.height + pad * 2
        frame = Image.new("RGB", (frame_w, frame_h), (24, 24, 27))
        frame.paste(cover_im, (pad, pad))
        x = (_OG_W - frame_w) // 2
        y = (_OG_H - frame_h) // 2 - 10
        bg.paste(frame, (x, y))

    # нижняя полоса бренда
    draw.rectangle((0, _OG_H - 56, _OG_W, _OG_H), fill=(18, 18, 22))
    draw.rectangle((0, _OG_H - 58, _OG_W, _OG_H - 56), fill=(234, 179, 8))
    try:
        from PIL import ImageFont

        font = ImageFont.load_default()
        draw.text(
            (40, _OG_H - 40),
            "sozdaipesnu.ru  ·  СоздайСвоюПесню",
            fill=(234, 179, 8),
            font=font,
        )
    except Exception:
        pass

    out = io.BytesIO()
    # progressive=False — baseline JPEG, надёжнее для превью-ботов
    bg.save(out, format="JPEG", quality=88, optimize=True, progressive=False)
    return out.getvalue()


def og_cache_path(cache_dir: Path, library_id: str) -> Path | None:
    tid = (library_id or "").strip()
    if not _SAFE_ID.match(tid):
        return None
    return cache_dir / f"{tid}.jpg"


def ensure_og_jpeg_file(
    *,
    library_id: str,
    cover_url: str,
    cache_dir: Path,
    fallback_path: Path | None = None,
    max_age_sec: int = _OG_CACHE_TTL_SEC,
) -> Path:
    """JPEG на диске: отдача через FileResponse (GET/HEAD) без сборки каждый раз."""
    path = og_cache_path(cache_dir, library_id)
    if path is None:
        raise ValueError("bad library_id")
    cache_dir.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size > 500:
        age = time.time() - path.stat().st_mtime
        if age < max_age_sec:
            return path
    jpeg = build_og_jpeg(cover_url=cover_url, fallback_path=fallback_path)
    if not jpeg or len(jpeg) < 500:
        raise RuntimeError("empty og jpeg")
    tmp = path.with_suffix(".jpg.tmp")
    tmp.write_bytes(jpeg)
    tmp.replace(path)
    return path
