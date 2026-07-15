import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "b1gto6f1fi6j2dpfdlhd")

# LLM: yandex | openai_compat (VseGPT / любой OpenAI-compatible)
# openai_compat: один ключ, разные model id под роли (тексты vs бот)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "yandex").strip().lower()
OPENAI_COMPAT_API_KEY = os.getenv("OPENAI_COMPAT_API_KEY", "").strip()
OPENAI_COMPAT_BASE = os.getenv(
    "OPENAI_COMPAT_BASE", "https://api.vsegpt.ru/v1"
).strip().rstrip("/")
# Роли (id из каталога провайдера, напр. VseGPT Docs/Models)
# PRO — сильная (lyrics, package); LITE — дешёвая (consultant, analyst fallback)
LLM_MODEL_PRO = os.getenv(
    "LLM_MODEL_PRO", "deepseek/deepseek-v4-pro"
).strip()
LLM_MODEL_LITE = os.getenv(
    "LLM_MODEL_LITE", "deepseek/deepseek-v4-flash"
).strip()

APIPASS_API_KEY = os.getenv("APIPASS_API_KEY", "")
APIPASS_BASE = os.getenv("APIPASS_BASE", "https://api.apipass.dev/api/v1/jobs")

# apipass | sunoapi | fallback (ApiPass→sunoapi) | fallback_suno (sunoapi→ApiPass)
MUSIC_PROVIDER = os.getenv("MUSIC_PROVIDER", "apipass").strip().lower()
SUNOAPI_ORG_API_KEY = os.getenv("SUNOAPI_ORG_API_KEY", "").strip()
SUNOAPI_ORG_BASE = os.getenv(
    "SUNOAPI_ORG_BASE", "https://api.sunoapi.org/api/v1"
).strip().rstrip("/")

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

# Бета-защита (без Redis; in-memory + SQLite). Мягче для 5–20 тестеров.
MAX_CONCURRENT_GENERATIONS = int(os.getenv("MAX_CONCURRENT_GENERATIONS", "6"))
MAX_CONCURRENT_PER_USER = int(os.getenv("MAX_CONCURRENT_PER_USER", "2"))
MAX_TRIAL_PER_IP_PER_DAY = int(os.getenv("MAX_TRIAL_PER_IP_PER_DAY", "8"))
# rate limit: запросов за окно
RATE_AUTH_IP_LIMIT = int(os.getenv("RATE_AUTH_IP_LIMIT", "8"))
RATE_AUTH_IP_WINDOW_SEC = int(os.getenv("RATE_AUTH_IP_WINDOW_SEC", "900"))  # 15 мин
RATE_GEN_IP_LIMIT = int(os.getenv("RATE_GEN_IP_LIMIT", "12"))
RATE_GEN_IP_WINDOW_SEC = int(os.getenv("RATE_GEN_IP_WINDOW_SEC", "60"))
RATE_MUSIC_IP_LIMIT = int(os.getenv("RATE_MUSIC_IP_LIMIT", "6"))
RATE_MUSIC_IP_WINDOW_SEC = int(os.getenv("RATE_MUSIC_IP_WINDOW_SEC", "60"))

SITE_URL = os.getenv("SITE_URL", "http://195.19.20.245:8000").rstrip("/")
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "stub").strip().lower()
GETPLATINUM_ACCOUNT = os.getenv("GETPLATINUM_ACCOUNT", "").strip()
GETPLATINUM_API_KEY = os.getenv("GETPLATINUM_API_KEY", "").strip()
GETPLATINUM_VAT = os.getenv("GETPLATINUM_VAT", "none").strip() or "none"
GETPLATINUM_POSITION_PREFIX = os.getenv("GETPLATINUM_POSITION_PREFIX", "").strip()
# IP-префиксы GetPlatinum для fallback-проверки webhook (через запятую).
# Реальные POST шли с 212.41.13.*
GETPLATINUM_WEBHOOK_IP_PREFIXES = os.getenv(
    "GETPLATINUM_WEBHOOK_IP_PREFIXES", "212.41.13."
).strip()

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "").strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}

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
TELEGRAM_AUTH_ENABLED = os.getenv("TELEGRAM_AUTH_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
}
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")

VK_AUTH_ENABLED = os.getenv("VK_AUTH_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
}
VK_APP_ID = os.getenv("VK_APP_ID", "").strip()
VK_APP_SECRET = os.getenv("VK_APP_SECRET", "").strip()
VK_AUTH_BASE = os.getenv("VK_AUTH_BASE", "https://id.vk.ru").strip().rstrip("/")

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

# --- Очередь задач (Redis) ---
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0").strip()
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "true").lower() in {"1", "true", "yes"}
WORKER_POLL_INTERVAL_SEC = int(os.getenv("WORKER_POLL_INTERVAL_SEC", "3"))
SQLITE_TIMEOUT_SEC = float(os.getenv("SQLITE_TIMEOUT_SEC", "30"))

# --- S3 (REG.RU Object Storage) ---
S3_ENABLED = os.getenv("S3_ENABLED", "false").lower() in {"1", "true", "yes"}
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "").strip()
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "").strip()
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "").strip()
S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
S3_REGION = os.getenv("S3_REGION", "ru-1").strip()
S3_PUBLIC_BASE = os.getenv("S3_PUBLIC_BASE", "").strip().rstrip("/")