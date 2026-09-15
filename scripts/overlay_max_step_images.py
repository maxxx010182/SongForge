"""Наложить русский заголовок на кадры шагов MAX (как на max-cover.jpg)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(
    r"C:\Users\makc0\.grok\sessions"
    r"\C%3A%5CUsers%5Cmakc0%5CDesktop%5CSongForge"
    r"\01a0a37d-0a03-7083-bd1f-9631e4bf556e\images"
)
OUT = ROOT / "assets"
W, H = 1080, 1350

STEPS = [
    ("5.jpg", "max-whom.jpg", "КОМУ ЭТА ПЕСНЯ", "ей, ему, маме — любому своему"),
    ("7.jpg", "max-occasion.jpg", "НА ЛЮБОЙ ПОВОД", "и без повода тоже"),
    ("4.jpg", "max-detail.jpg", "ОДНА ЖИВАЯ ЧЕРТА", "то, что знаете только вы"),
    ("1.jpg", "max-genre.jpg", "КАК ЭТО ЗВУЧИТ", "ваш саундтрек"),
    ("6.jpg", "max-mood.jpg", "КАКОЕ ЧУВСТВО", "тепло, романтика, мурашки"),
    ("2.jpg", "max-voice.jpg", "ЧЕЙ ГОЛОС", "её, его, вместе"),
    ("3.jpg", "max-confirm.jpg", "ТАК?", "можно поправить"),
]


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\ARIALBD.TTF" if bold else r"C:\Windows\Fonts\ARIAL.TTF",
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\calibrib.ttf" if bold else r"C:\Windows\Fonts\calibri.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _fit(im: Image.Image) -> Image.Image:
    im = im.convert("RGB")
    src_w, src_h = im.size
    scale = max(W / src_w, H / src_h)
    nw, nh = int(src_w * scale), int(src_h * scale)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - W) // 2
    top = (nh - H) // 2
    return im.crop((left, top, left + W, top + H))


def overlay(src: Path, title: str, sub: str) -> Image.Image:
    base = _fit(Image.open(src))
    shade = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(shade)
    for y in range(0, 430):
        alpha = int(200 * (1 - y / 430) ** 1.15)
        sd.line([(0, y), (W, y)], fill=alpha)
    shade = shade.filter(ImageFilter.GaussianBlur(8))
    black = Image.new("RGB", (W, H), (0, 0, 0))
    base = Image.composite(black, base, shade)

    draw = ImageDraw.Draw(base)
    title_font = _font(64)
    sub_font = _font(36, bold=True)

    def centered(text: str, font: ImageFont.FreeTypeFont, y: int, fill) -> None:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) / 2, y), text, font=font, fill=fill)

    # shrink title if too wide
    while draw.textbbox((0, 0), title, font=title_font)[2] > W - 80:
        title_font = _font(title_font.size - 2)

    centered(title, title_font, 72, (255, 255, 255))
    tb = draw.textbbox((0, 0), title, font=title_font)
    line_y = 72 + (tb[3] - tb[1]) + 22
    pad = 160
    draw.line([(pad, line_y), (W - pad, line_y)], fill=(234, 179, 8), width=3)
    while draw.textbbox((0, 0), sub, font=sub_font)[2] > W - 80:
        sub_font = _font(sub_font.size - 2, bold=True)
    centered(sub, sub_font, line_y + 28, (250, 204, 21))
    return base


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for src_name, dest_name, title, sub in STEPS:
        src = SRC / src_name
        if not src.is_file():
            raise SystemExit(f"missing {src}")
        img = overlay(src, title, sub)
        dest = OUT / dest_name
        img.save(dest, "JPEG", quality=90, optimize=True)
        print(f"wrote {dest.name} {dest.stat().st_size}")


if __name__ == "__main__":
    main()
