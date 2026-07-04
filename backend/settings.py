import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "b1gto6f1fi6j2dpfdlhd")

APIPASS_API_KEY = os.getenv("APIPASS_API_KEY", "")
APIPASS_BASE = os.getenv("APIPASS_BASE", "https://api.apipass.dev/api/v1/jobs")

DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "songforge.db"
UPLOADS_DIR = DATA_DIR / "uploads"
AVATARS_DIR = UPLOADS_DIR / "avatars"
MAX_AVATAR_BYTES = 2 * 1024 * 1024

DEFAULT_MODEL_VERSION = "V5_5"
DEFAULT_CHANNEL = "auto"
DEFAULT_STYLE_WEIGHT = 0.85
DEFAULT_WEIRDNESS = 0.20
DEFAULT_AUDIO_WEIGHT = 0.70

MUSIC_POLL_INTERVAL_SEC = 10
MUSIC_MAX_WAIT_SEC = 360

GUEST_GENERATION_LIMIT = 1
SESSION_TTL_DAYS = 30
SHOWCASE_HOURS = 24
PREVIEW_LIMIT_SEC = 30
PREVIEW_MAX_BYTES = 500_000

SITE_URL = os.getenv("SITE_URL", "http://195.19.20.245:8000").rstrip("/")
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "stub").strip().lower()
PRODAMUS_SECRET = os.getenv("PRODAMUS_SECRET", "")
PRODAMUS_SHOP_ID = os.getenv("PRODAMUS_SHOP_ID", "")

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()

AUTH_DEV_CODE_ENABLED = os.getenv("AUTH_DEV_CODE_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
}
LEGACY_API_ENABLED = os.getenv("LEGACY_API_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
}
DEV_TOPUP_ENABLED = os.getenv("DEV_TOPUP_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
}
TELEGRAM_AUTH_ENABLED = os.getenv("TELEGRAM_AUTH_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
}

# --- Админ-панель (/admin) ---
# Только эти email при первом входе в /admin становятся super_admin (через запятую).
ADMIN_BOOTSTRAP_EMAILS: frozenset[str] = frozenset(
    e.strip().lower()
    for e in os.getenv("ADMIN_BOOTSTRAP_EMAILS", "").split(",")
    if e.strip()
)
# Пусто = без ограничения по IP. Иначе только перечисленные IP (через запятую).
ADMIN_IP_ALLOWLIST: frozenset[str] = frozenset(
    ip.strip()
    for ip in os.getenv("ADMIN_IP_ALLOWLIST", "").split(",")
    if ip.strip()
)