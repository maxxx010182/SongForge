"""Карточка 1200x630 для превью ссылки (Telegram / WhatsApp / VK)."""

from __future__ import annotations

import hashlib
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
_GIFT_OG_ID = re.compile(r"^gift-[a-fA-F0-9-]{8,40}-[a-fA-F0-9]{8,16}$")
_GIFT_OG_REV = "128"
_ROOT = Path(__file__).resolve().parent.parent
_FONTS = _ROOT / "assets" / "fonts"
_GIFT_BG = _ROOT / "assets" / "gift"
_ACCENT = {
    "family": (232, 184, 109),
    "love": (224, 112, 126),
    "birthday": (245, 197, 66),
    "simple": (234, 179, 8),
}


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


def _cyr_font(size: int, bold: bool = False):
    from PIL import ImageFont

    name = "NotoSans-Bold.ttf" if bold else "NotoSans-Regular.ttf"
    bundled = _FONTS / name
    if bundled.is_file():
        return ImageFont.truetype(str(bundled), size)
    fallbacks = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf"),
    )
    for path in fallbacks:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _wrap_text(draw, text: str, font, max_width: int, limit: int = 4) -> list[str]:
    lines: list[str] = []
    paras = [p.strip() for p in (text or "").split("\n") if p.strip()]
    if not paras:
        return []
    for para in paras:
        current = ""
        for word in para.split():
            trial = (current + " " + word).strip()
            if draw.textlength(trial, font=font) <= max_width:
                current = trial
                continue
            if current:
                lines.append(current)
            current = word
            if len(lines) >= limit:
                return lines[:limit]
        if current and len(lines) < limit:
            lines.append(current)
        if len(lines) >= limit:
            break
    return lines[:limit]


def _cover_square(cover_url: str, fallback_path: Path | None, side: int):
    from PIL import Image, ImageDraw

    cover_bytes = _fetch_bytes(cover_url)
    cover_im = None
    if cover_bytes:
        try:
            cover_im = Image.open(io.BytesIO(cover_bytes)).convert("RGB")
        except Exception as exc:
            log.warning("gift og cover open failed: %s", exc)
            cover_im = None
    if cover_im is None and fallback_path and fallback_path.is_file():
        try:
            cover_im = Image.open(fallback_path).convert("RGB")
        except Exception:
            cover_im = None
    if cover_im is None:
        return None
    cover_im = cover_im.copy()
    cover_im.thumbnail((side, side), Image.Resampling.LANCZOS)
    mask = Image.new("L", cover_im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, cover_im.size[0] - 1, cover_im.size[1] - 1),
        radius=28,
        fill=255,
    )
    rounded = Image.new("RGB", cover_im.size, (12, 10, 8))
    rounded.paste(cover_im, (0, 0))
    out = Image.new("RGBA", cover_im.size, (0, 0, 0, 0))
    out.paste(rounded, (0, 0))
    out.putalpha(mask)
    return out


def _theme_background(occasion: str):
    from PIL import Image

    key = occasion if occasion in ("family", "love", "birthday", "simple") else "simple"
    wide = _GIFT_BG / f"{key}-wide.jpg"
    portrait = _GIFT_BG / f"{key}.jpg"
    src = wide if wide.is_file() else portrait
    if src.is_file():
        im = Image.open(src).convert("RGB")
        # cover 1200x630
        scale = max(_OG_W / im.width, _OG_H / im.height)
        nw, nh = int(im.width * scale), int(im.height * scale)
        im = im.resize((nw, nh), Image.Resampling.LANCZOS)
        left = (nw - _OG_W) // 2
        top = (nh - _OG_H) // 2
        return im.crop((left, top, left + _OG_W, top + _OG_H))
    return Image.new("RGB", (_OG_W, _OG_H), (12, 10, 8))


def gift_og_version(*, occasion: str, to_line: str, from_line: str, title: str) -> str:
    raw = f"{_GIFT_OG_REV}|{occasion}|{to_line}|{from_line}|{title}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def build_gift_og_jpeg(
    *,
    occasion: str,
    to_line: str,
    from_line: str,
    title: str,
    cover_url: str,
    fallback_path: Path | None = None,
) -> bytes:
    from PIL import Image, ImageDraw

    heading = (to_line or "").strip() or "Тебе"
    sign = (from_line or "").strip()
    title_s = (title or "").strip() or "Песня"
    accent = _ACCENT.get(occasion, _ACCENT["simple"])

    bg = _theme_background(occasion).convert("RGBA")
    shade = Image.new("RGBA", (_OG_W, _OG_H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for x in range(0, 760):
        alpha = int(170 * (1 - x / 760))
        sd.line([(x, 0), (x, _OG_H)], fill=(0, 0, 0, alpha))
    sd.rectangle((0, _OG_H - 70, _OG_W, _OG_H), fill=(0, 0, 0, 90))
    card = Image.alpha_composite(bg, shade).convert("RGB")
    draw = ImageDraw.Draw(card)

    heading_size = 42 if len(heading) > 48 else 64
    wrap_limit = 5 if len(heading) > 48 else 3
    font_h = _cyr_font(heading_size, bold=True)
    font_t = _cyr_font(32, bold=False)
    font_s = _cyr_font(28, bold=False)
    font_b = _cyr_font(20, bold=False)

    text_w = 640
    y = 72 if heading_size < 64 else 88
    line_h = 52 if heading_size < 64 else 74
    for line in _wrap_text(draw, heading, font_h, text_w, wrap_limit):
        draw.text((64, y), line, fill=(255, 248, 236), font=font_h)
        y += line_h
    y += 10
    draw.rectangle((64, y, 64 + 72, y + 4), fill=accent)
    y += 28
    for line in _wrap_text(draw, title_s, font_t, text_w, 2):
        draw.text((64, y), line, fill=(232, 220, 200), font=font_t)
        y += 40
    if sign:
        y += 18
        draw.text((64, y), sign, fill=accent, font=font_s)

    cover = _cover_square(cover_url, fallback_path, 360)
    if cover is not None:
        cx = _OG_W - cover.size[0] - 72
        cy = (_OG_H - cover.size[1]) // 2 - 8
        card.paste(cover.convert("RGB"), (cx, cy), cover)

    draw.text(
        (64, _OG_H - 42),
        "sozdaipesnu.ru  ·  СоздайСвоюПесню",
        fill=accent,
        font=font_b,
    )

    out = io.BytesIO()
    card.save(out, format="JPEG", quality=88, optimize=True, progressive=False)
    return out.getvalue()


def ensure_gift_og_jpeg_file(
    *,
    gift_id: str,
    occasion: str,
    to_line: str,
    from_line: str,
    title: str,
    cover_url: str,
    cache_dir: Path,
    fallback_path: Path | None = None,
    max_age_sec: int = _OG_CACHE_TTL_SEC,
) -> Path:
    ver = gift_og_version(
        occasion=occasion, to_line=to_line, from_line=from_line, title=title
    )
    key = f"gift-{gift_id}-{ver}"
    if not _GIFT_OG_ID.match(key):
        raise ValueError("bad gift og id")
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.jpg"
    if path.is_file() and path.stat().st_size > 500:
        age = time.time() - path.stat().st_mtime
        if age < max_age_sec:
            return path
    jpeg = build_gift_og_jpeg(
        occasion=occasion,
        to_line=to_line,
        from_line=from_line,
        title=title,
        cover_url=cover_url,
        fallback_path=fallback_path,
    )
    if not jpeg or len(jpeg) < 500:
        raise RuntimeError("empty gift og jpeg")
    tmp = path.with_suffix(".jpg.tmp")
    tmp.write_bytes(jpeg)
    tmp.replace(path)
    return path
