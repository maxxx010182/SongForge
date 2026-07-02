#!/bin/bash
# SongForge — обновление на VPS (без git)
# Запуск: bash scripts/deploy-vps.sh

set -e

BASE="https://raw.githubusercontent.com/maxxx010182/SongForge/main"
CACHE_BUST="?$(date +%s)"
DIR="${HOME}/SongForge"
EXPECTED_VERSION="2.2.0"

strip_crlf() {
  local f="$1"
  [ -f "$f" ] || return 0
  sed -i 's/\r$//' "$f" 2>/dev/null || tr -d '\r' <"$f" >"$f.tmp" && mv -f "$f.tmp" "$f"
}

download() {
  local out="$1"
  local url="$2"
  wget -q -O "$out" "${url}${CACHE_BUST}" || curl -fsSL -o "$out" "${url}${CACHE_BUST}"
  strip_crlf "$out"
}

echo "=== SongForge deploy ==="
cd "$DIR" || { echo "Папка $DIR не найдена!"; exit 1; }

mkdir -p backend/services backend/utils backend/database scripts

echo "[1/7] Скачиваем файлы с GitHub..."
download app.py "$BASE/app.py"
download index.html "$BASE/index.html"

download backend/app.py "$BASE/backend/app.py"
download backend/models.py "$BASE/backend/models.py"
download backend/settings.py "$BASE/backend/settings.py"
download backend/logger.py "$BASE/backend/logger.py"
download backend/utils/text.py "$BASE/backend/utils/text.py"
download backend/database/db.py "$BASE/backend/database/db.py"
download backend/services/ai_producer.py "$BASE/backend/services/ai_producer.py"
download backend/services/prompt_builder.py "$BASE/backend/services/prompt_builder.py"
download backend/services/apipass_client.py "$BASE/backend/services/apipass_client.py"
download backend/services/ai_music_analyst.py "$BASE/backend/services/ai_music_analyst.py"
download backend/services/ai_prompt_composer.py "$BASE/backend/services/ai_prompt_composer.py"
download backend/services/reference_translator.py "$BASE/backend/services/reference_translator.py"
download backend/services/style_enforcer.py "$BASE/backend/services/style_enforcer.py"
download backend/services/plan_overrides.py "$BASE/backend/services/plan_overrides.py"
download backend/services/genre_resolver.py "$BASE/backend/services/genre_resolver.py"
download backend/services/idea_parser.py "$BASE/backend/services/idea_parser.py"
download backend/services/yandex_client.py "$BASE/backend/services/yandex_client.py"
download backend/services/history.py "$BASE/backend/services/history.py"
download backend/services/guest_service.py "$BASE/backend/services/guest_service.py"
download backend/services/auth_service.py "$BASE/backend/services/auth_service.py"
download backend/services/cabinet_service.py "$BASE/backend/services/cabinet_service.py"
download backend/services/profile_service.py "$BASE/backend/services/profile_service.py"
download backend/services/consultant.py "$BASE/backend/services/consultant.py"

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
./venv/bin/pip install -q python-multipart 2>/dev/null || ./venv/bin/pip install python-multipart

echo "[3/7] Очищаем Python cache..."
find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

echo "[4/7] Проверяем Python..."
./venv/bin/python -c "
from backend.database.db import init_db
from backend.services.guest_service import GuestService
from backend.services.auth_service import AuthService
from backend.services.cabinet_service import CabinetService
from backend.services.profile_service import ProfileService
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
"

echo "[5/7] Освобождаем порт 8000..."
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8000/tcp 2>/dev/null || true
elif command -v lsof >/dev/null 2>&1; then
  for pid in $(lsof -t -i:8000 2>/dev/null); do
    kill "$pid" 2>/dev/null || true
  done
else
  pkill -f "${DIR}/app.py" 2>/dev/null || true
fi
sleep 2

echo "[6/7] Перезапускаем PM2..."
pm2 delete songforge 2>/dev/null || true
pm2 start app.py --name songforge --interpreter ./venv/bin/python --cwd "$DIR"
pm2 save

echo "[7/7] Проверяем health..."
sleep 3
HEALTH="$(curl -s http://127.0.0.1:8000/api/health)"
echo "$HEALTH"
if ! echo "$HEALTH" | grep -q "\"version\":\"$EXPECTED_VERSION\""; then
  echo ""
  echo "ОШИБКА: ожидалась версия $EXPECTED_VERSION"
  (ss -lptn 'sport = :8000' 2>/dev/null || netstat -tlnp 2>/dev/null | grep 8000 || true)
  pm2 logs songforge --lines 30 --nostream
  exit 1
fi

echo "[+] Обновляем скрипт деплоя на следующий раз..."
download scripts/deploy-vps.sh "$BASE/scripts/deploy-vps.sh"
chmod +x scripts/deploy-vps.sh

echo ""
echo "=== Готово! v$EXPECTED_VERSION — http://195.19.20.245:8000/ ==="