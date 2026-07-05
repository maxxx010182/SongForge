"""Embed logo PNGs as base64 data URIs into index.html."""
from __future__ import annotations

import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"

LOGOS = {
    "favicon": ROOT / "assets" / "logo-64.png",
    "header": ROOT / "assets" / "logo-header.png",
    "header2x": ROOT / "assets" / "logo-header@2x.png",
    "gen": ROOT / "assets" / "logo-gen.png",
}


def data_uri(path: Path) -> str:
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{payload}"


def main() -> None:
    uris = {key: data_uri(path) for key, path in LOGOS.items()}
    html = INDEX.read_text(encoding="utf-8")

    html = re.sub(
        r'<link rel="icon" href="[^"]*" type="image/png">',
        f'<link rel="icon" href="{uris["favicon"]}" type="image/png">',
        html,
        count=1,
    )

    html = re.sub(
        r'<img src="/assets/logo-header\.png[^"]*" srcset="[^"]*" alt="СоздайСвоюПесню"[^>]*>',
        (
            f'<img src="{uris["header"]}" '
            f'srcset="{uris["header"]} 1x, {uris["header2x"]} 2x" '
            f'alt="СоздайСвоюПесню" class="logo-img" width="36" height="36" decoding="async" fetchpriority="high">'
        ),
        html,
        count=1,
    )

    html = re.sub(
        r'<img src="/assets/logo-gen\.png[^"]*" alt="" class="logo-img"[^>]*>',
        (
            f'<img src="{uris["gen"]}" alt="" class="logo-img" '
            f'width="64" height="64" decoding="async">'
        ),
        html,
        count=1,
    )

    INDEX.write_text(html, encoding="utf-8")
    print(f"Embedded logos into {INDEX} ({INDEX.stat().st_size} bytes)")


if __name__ == "__main__":
    main()