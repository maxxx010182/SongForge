#!/bin/bash
# SongForge — обновление на VPS (без git)
# deploy-script-version: 8
# Запуск: bash scripts/deploy-vps.sh
# Скачать (обход кэша raw.githubusercontent.com):
# curl -fsSL -H "Accept: application/vnd.github.raw" \
#   "https://api.github.com/repos/maxxx010182/SongForge/contents/scripts/deploy-vps.sh?ref=main" \
#   -o scripts/deploy-vps.sh

set -e

GH_API="https://api.github.com/repos/maxxx010182/SongForge/contents"
DIR="${HOME}/SongForge"
EXPECTED_VERSION="2.4.0"

strip_crlf() {
  local f="$1"
  [ -f "$f" ] || return 0
  # Linux VPS: только sed, без .tmp/mv (старый fallback ломал деплой)
  sed -i 's/\r$//' "$f" 2>/dev/null || true
}

download() {
  local out="$1"
  local repo_path="$2"
  curl -fsSL -H "Accept: application/vnd.github.raw" \
    "${GH_API}/${repo_path}?ref=main" \
    -o "$out"
  if [ ! -s "$out" ]; then
    echo "ОШИБКА: не скачан или пустой файл: $out"
    exit 1
  fi
  strip_crlf "$out"
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

echo "=== SongForge deploy ==="
cd "$DIR" || { echo "Папка $DIR не найдена!"; exit 1; }

mkdir -p backend/services backend/utils backend/database scripts assets

echo "[1/7] Скачиваем файлы с GitHub (API, без кэша)..."
download app.py app.py
download requirements.txt requirements.txt
download index.html index.html
download SongForgeLogo.png SongForgeLogo.png
if [ ! -s SongForgeLogo.png ]; then
  echo "ОШИБКА: SongForgeLogo.png не скачан"
  exit 1
fi

download assets/logo-header.png assets/logo-header.png
download assets/logo-header@2x.png assets/logo-header@2x.png
download assets/logo-gen.png assets/logo-gen.png
for f in assets/logo-header.png assets/logo-header@2x.png assets/logo-gen.png; do
  if [ ! -s "$f" ]; then
    echo "ОШИБКА: не скачан $f"
    exit 1
  fi
done

download backend/app.py backend/app.py
download backend/models.py backend/models.py
download backend/settings.py backend/settings.py
download backend/logger.py backend/logger.py
download backend/utils/text.py backend/utils/text.py
download backend/database/db.py backend/database/db.py
download backend/services/ai_producer.py backend/services/ai_producer.py
download backend/services/prompt_builder.py backend/services/prompt_builder.py
download backend/services/apipass_client.py backend/services/apipass_client.py
download backend/services/ai_music_analyst.py backend/services/ai_music_analyst.py
download backend/services/ai_prompt_composer.py backend/services/ai_prompt_composer.py
download backend/services/reference_translator.py backend/services/reference_translator.py
download backend/services/style_enforcer.py backend/services/style_enforcer.py
download backend/services/plan_overrides.py backend/services/plan_overrides.py
download backend/services/genre_resolver.py backend/services/genre_resolver.py
download backend/services/idea_parser.py backend/services/idea_parser.py
download backend/services/yandex_client.py backend/services/yandex_client.py
download backend/services/history.py backend/services/history.py
download backend/services/guest_service.py backend/services/guest_service.py
download backend/services/auth_service.py backend/services/auth_service.py
download backend/services/cabinet_service.py backend/services/cabinet_service.py
download backend/services/profile_service.py backend/services/profile_service.py
download backend/services/generation_quota_service.py backend/services/generation_quota_service.py
download backend/services/consultant.py backend/services/consultant.py
download backend/services/audio_access_service.py backend/services/audio_access_service.py
download backend/services/payment_service.py backend/services/payment_service.py

for f in \
  backend/services/genre_resolver.py \
  backend/services/idea_parser.py \
  backend/services/plan_overrides.py \
  backend/services/style_enforcer.py; do
  if [ ! -s "$f" ]; then
    echo "ОШИБКА: не скачан $f"
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
if ! grep -q 'data:image/png;base64,' index.html; then
  echo "ОШИБКА: index.html без встроенного логотипа (base64)"
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
echo ""
echo "Скрипт деплоя скачай отдельно (см. инструкцию в начале файла deploy-vps.sh)."