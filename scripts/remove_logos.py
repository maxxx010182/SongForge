"""Remove heart+note PNG logos from index.html; use title + FA icon instead."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"

FAVICON = (
    '<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' '
    "viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%2309090b'/%3E"
    "%3Cpath fill='%23eab308' d='M19 7v13.2c-.9-.6-2-.9-3.1-.9-2.5 0-4.5 1.6-4.5 3.6s2 3.6 "
    "4.5 3.6 4.5-1.6 4.5-3.6V10.8l-5.5-1.6z'/%3E%3C/svg%3E\" type=\"image/svg+xml\">"
)

HEADER = """<div class="flex items-center gap-3 justify-self-start">
        <span id="headerBrand" class="font-title text-3xl font-semibold tracking-tighter neon-text text-yellow-400 cursor-pointer select-none">СоздайСвоюПесню</span>
    </div>
    <nav class="header-nav"""

GEN = """<div id="genLogo" class="w-16 h-16 rounded-3xl flex items-center justify-center pulse-logo ring-2 ring-yellow-400/30 bg-white/5">
                    <i class="fa-solid fa-wand-magic-sparkles text-3xl text-yellow-400"></i>
                </div>"""


def main() -> None:
    html = INDEX.read_text(encoding="utf-8")

    html = re.sub(
        r'<link rel="icon" href="[^"]*" type="image/(?:png|svg\+xml)">',
        FAVICON,
        html,
        count=1,
    )

    m = re.search(
        r'<div class="flex items-center gap-3 justify-self-start">.*?</div>\s*<nav class="header-nav',
        html,
        re.S,
    )
    if not m:
        raise SystemExit("header block not found")
    tail = html[m.end() :]
    if tail.lstrip().startswith('<nav class="header-nav'):
        tail = tail[tail.index("<nav class=\"header-nav\") + len('<nav class="header-nav') :]
    html = html[: m.start()] + HEADER + tail

    html, n = re.subn(
        r'<div id="genLogo" class="logo-slot w-16 h-16[^"]*">\s*<img[^>]*>\s*</div>',
        GEN,
        html,
        count=1,
    )
    if n != 1:
        raise SystemExit(f"genLogo replace count={n}")

    html = html.replace("getElementById('headerLogo')", "getElementById('headerBrand')")

    INDEX.write_text(html, encoding="utf-8")
    print(f"Updated {INDEX} ({INDEX.stat().st_size} bytes)")


if __name__ == "__main__":
    main()