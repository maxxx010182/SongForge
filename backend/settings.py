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

DEV_TOPUP_ENABLED = os.getenv("DEV_TOPUP_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
}