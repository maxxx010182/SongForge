"""Legal HTML fragments for /legal/* pages (legal_pages.py).

Since v2.11.1 embedded legal text is no longer injected into index.html —
the SPA links to /legal/terms, /legal/privacy, /legal/offer instead.

Workflow:
  python scripts/md_legal_to_html.py
  # fragments land in scripts/legal_html/*.html — served by backend/legal_pages.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGAL = ROOT / "scripts" / "legal_html"

REQUIRED = ("agreement.html", "privacy.html", "offer.html")


def main() -> None:
    missing = [name for name in REQUIRED if not (LEGAL / name).is_file()]
    if missing:
        raise SystemExit(
            "Missing legal HTML: "
            + ", ".join(missing)
            + "\nRun: python scripts/md_legal_to_html.py"
        )
    print("OK: scripts/legal_html/*.html ready for /legal/* (index.html not patched)")


if __name__ == "__main__":
    main()