#!/bin/bash
# SongForge — обновление на VPS (без git)
# deploy-script-version: 11
# Запуск: bash scripts/deploy-vps.sh

set -e

DIR="${HOME}/SongForge"
EXPECTED_VERSION="2.5.1"
ARCHIVE_URL="https://codeload.github.com/maxxx010182/SongForge/tar.gz/main"

strip_crlf() {
  local f="$1"
  [ -f "$f" ] || return 0
  sed -i 's/\r$//' "$f" 2>/dev/null || true
}

fetch_archive() {
  local out="$1"
  local bust="?$(date +%s)"
  curl -fsSL "${ARCHIVE_URL}${bust}" -o "$out" \
    || wget -q -O "$out" "${ARCHIVE_URL}${bust}" \
    || curl -fsSL "https://github.com/maxxx010182/SongForge/archive/refs/heads/main.tar.gz${bust}" -o "$out"
}

sync_from_src() {
  local src="$1"
  local dst="$2"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a \
      --exclude 'data/' \
      --exclude 'venv/' \
      --exclude '.env' \
      --exclude '.git/' \
      "$src/" "$dst/"
    return 0
  fi
  for path in "$src"/*; do
    [ -e "$path" ] || continue
    local base
    base=$(basename "$path")
    case "$base" in
      data|venv|.env|.git) continue ;;
    esac
    cp -a "$path" "$dst/"
  done
}

ensure_venv() {
  if [ -x "./venv/bin/python" ] && ./venv/bin/python -c "import sys; sys.exit(0)" 2>/dev/null; then
    return 0
  fi
  echo "  Python-окружение сломано или отсутствует — создаём заново..."
  rm -rf venv
  python3 -m venv venv
  ./venv/bin/pip install -q --upgrade pip
  if [ -f requirements.txt ]; then
    ./venv/bin/pip install -q -r requirements.txt
  else
    ./venv/bin/pip install -q fastapi uvicorn python-dotenv requests pydantic python-multipart
  fi
}

echo "=== SongForge deploy (deploy-script-version: 11) ==="
mkdir -p "$DIR"
cd "$DIR" || { echo "Папка $DIR не найдена!"; exit 1; }

mkdir -p backend/services backend/utils backend/database scripts assets data

echo "[1/7] Скачиваем архив с GitHub (1 запрос, без лимита API)..."
TMP=$(mktemp -d)
ARCHIVE="$TMP/repo.tar.gz"
if ! fetch_archive "$ARCHIVE"; then
  echo "ОШИБКА: не удалось скачать архив репозитория"
  rm -rf "$TMP"
  exit 1
fi
if [ ! -s "$ARCHIVE" ]; then
  echo "ОШИБКА: пустой архив"
  rm -rf "$TMP"
  exit 1
fi

tar -xzf "$ARCHIVE" -C "$TMP"
SRC=$(find "$TMP" -maxdepth 1 -type d -name 'SongForge-*' | head -1)
if [ -z "$SRC" ]; then
  echo "ОШИБКА: не найдена папка SongForge-* после распаковки"
  rm -rf "$TMP"
  exit 1
fi

echo "  Распаковано из: $(basename "$SRC")"
sync_from_src "$SRC" "$DIR"
find "$DIR/scripts" -name '*.sh' -exec strip_crlf {} \; 2>/dev/null || true
rm -rf "$TMP"

for f in app.py index.html requirements.txt backend/app.py SongForgeLogo.png; do
  if [ ! -s "$f" ]; then
    echo "ОШИБКА: после синхронизации нет файла $f"
    exit 1
  fi
done

echo "[2/7] Зависимости..."
ensure_venv
./venv/bin/pip install -q -r requirements.txt 2>/dev/null || ./venv/bin/pip install -r requirements.txt

echo "[3/7] Очищаем Python cache..."
find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

echo "[4/7] Проверяем файлы и Python..."
if ! grep -qF "$EXPECTED_VERSION" backend/app.py; then
  echo "ОШИБКА: backend/app.py не содержит версию $EXPECTED_VERSION"
  grep version backend/app.py | head -3 || true
  exit 1
fi
if ! grep -q 'SongForgeLogo.png' index.html; then
  echo "ОШИБКА: index.html не ссылается на SongForgeLogo.png"
  exit 1
fi
if [ ! -s SongForgeLogo.png ]; then
  echo "ОШИБКА: нет файла SongForgeLogo.png в корне проекта"
  exit 1
fi
./venv/bin/python -c "
from backend.database.db import init_db
from backend.services.guest_service import GuestService
from backend.services.auth_service import AuthService
from backend.services.cabinet_service import CabinetService
from backend.services.profile_service import ProfileService
from backend.services.generation_quota_service import GenerationQuotaService
from backend.services.idea_parser import parse_idea
from backend.services.genre_resolver import resolve_genre
from backend.services.plan_overrides import apply_user_to_plan
from backend.services.style_enforcer import enforce_style
from backend.services.ai_music_analyst import AiMusicAnalyst
from backend.services.prompt_builder import PromptBuilder
from backend.app import app
init_db()
print('import OK')
print('app version:', app.version)
if app.version != '$EXPECTED_VERSION':
    raise SystemExit('wrong app version on disk')
"

free_port_8000() {
  pm2 delete songforge 2>/dev/null || true
  pm2 stop songforge 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    if command -v fuser >/dev/null 2>&1; then
      fuser -k 8000/tcp 2>/dev/null || true
    fi
    if command -v lsof >/dev/null 2>&1; then
      for pid in $(lsof -t -i:8000 2>/dev/null); do
        kill -9 "$pid" 2>/dev/null || true
      done
    fi
    pkill -9 -f "uvicorn.*8000" 2>/dev/null || true
    pkill -9 -f "${DIR}/app.py" 2>/dev/null || true
    pkill -9 -f "SongForge/app.py" 2>/dev/null || true
    sleep 1
    if ! (ss -lptn 'sport = :8000' 2>/dev/null | grep -q ':8000'); then
      return 0
    fi
  done
  return 1
}

start_songforge() {
  cd "$DIR"
  pm2 start app.py --name songforge --interpreter ./venv/bin/python --cwd "$DIR"
  pm2 save
}

echo "[5/7] Освобождаем порт 8000..."
if ! free_port_8000; then
  echo "ОШИБКА: порт 8000 всё ещё занят:"
  ss -lptn 'sport = :8000' 2>/dev/null || netstat -tlnp 2>/dev/null | grep 8000 || true
  exit 1
fi

echo "[6/7] Запускаем PM2..."
start_songforge

echo "[7/7] Проверяем health..."
sleep 4
HEALTH="$(curl -s http://127.0.0.1:8000/api/health)"
echo "$HEALTH"
if ! echo "$HEALTH" | grep -q "\"version\":\"$EXPECTED_VERSION\""; then
  echo ""
  echo "Повтор: убиваем старый процесс и перезапускаем..."
  free_port_8000 || true
  start_songforge
  sleep 4
  HEALTH="$(curl -s http://127.0.0.1:8000/api/health)"
  echo "$HEALTH"
fi
if ! echo "$HEALTH" | grep -q "\"version\":\"$EXPECTED_VERSION\""; then
  echo ""
  echo "ОШИБКА: ожидалась версия $EXPECTED_VERSION"
  (ss -lptn 'sport = :8000' 2>/dev/null || netstat -tlnp 2>/dev/null | grep 8000 || true)
  pm2 logs songforge --lines 30 --nostream
  exit 1
fi

echo ""
echo "=== Готово! v$EXPECTED_VERSION — http://195.19.20.245:8000/ ==="