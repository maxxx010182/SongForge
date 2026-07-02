#!/bin/bash
# SongForge — обновление на VPS (без git)
# Запуск: bash scripts/deploy-vps.sh

set -e

BASE="https://raw.githubusercontent.com/maxxx010182/SongForge/main"
CACHE_BUST="?$(date +%s)"
DIR="${HOME}/SongForge"
EXPECTED_VERSION="2.1.4"

echo "=== SongForge deploy ==="
cd "$DIR" || { echo "Папка $DIR не найдена!"; exit 1; }

mkdir -p backend/services backend/utils backend/database scripts

echo "[0/5] Обновляем скрипт деплоя..."
wget -q -O scripts/deploy-vps.sh "$BASE/scripts/deploy-vps.sh$CACHE_BUST"
chmod +x scripts/deploy-vps.sh

echo "[1/5] Скачиваем файлы с GitHub..."
wget -q -O app.py "$BASE/app.py$CACHE_BUST"
wget -q -O index.html "$BASE/index.html$CACHE_BUST"

wget -q -O backend/app.py "$BASE/backend/app.py$CACHE_BUST"
wget -q -O backend/models.py "$BASE/backend/models.py$CACHE_BUST"
wget -q -O backend/settings.py "$BASE/backend/settings.py$CACHE_BUST"
wget -q -O backend/logger.py "$BASE/backend/logger.py$CACHE_BUST"
wget -q -O backend/utils/text.py "$BASE/backend/utils/text.py$CACHE_BUST"
wget -q -O backend/database/db.py "$BASE/backend/database/db.py$CACHE_BUST"
wget -q -O backend/services/ai_producer.py "$BASE/backend/services/ai_producer.py$CACHE_BUST"
wget -q -O backend/services/prompt_builder.py "$BASE/backend/services/prompt_builder.py$CACHE_BUST"
wget -q -O backend/services/apipass_client.py "$BASE/backend/services/apipass_client.py$CACHE_BUST"
wget -q -O backend/services/ai_music_analyst.py "$BASE/backend/services/ai_music_analyst.py$CACHE_BUST"
wget -q -O backend/services/ai_prompt_composer.py "$BASE/backend/services/ai_prompt_composer.py$CACHE_BUST"
wget -q -O backend/services/reference_translator.py "$BASE/backend/services/reference_translator.py$CACHE_BUST"
wget -q -O backend/services/style_enforcer.py "$BASE/backend/services/style_enforcer.py$CACHE_BUST"
wget -q -O backend/services/plan_overrides.py "$BASE/backend/services/plan_overrides.py$CACHE_BUST"
wget -q -O backend/services/genre_resolver.py "$BASE/backend/services/genre_resolver.py$CACHE_BUST"
wget -q -O backend/services/idea_parser.py "$BASE/backend/services/idea_parser.py$CACHE_BUST"
wget -q -O backend/services/yandex_client.py "$BASE/backend/services/yandex_client.py$CACHE_BUST"
wget -q -O backend/services/history.py "$BASE/backend/services/history.py$CACHE_BUST"
wget -q -O backend/services/guest_service.py "$BASE/backend/services/guest_service.py$CACHE_BUST"
wget -q -O backend/services/auth_service.py "$BASE/backend/services/auth_service.py$CACHE_BUST"
wget -q -O backend/services/cabinet_service.py "$BASE/backend/services/cabinet_service.py$CACHE_BUST"
wget -q -O backend/services/consultant.py "$BASE/backend/services/consultant.py$CACHE_BUST"

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

echo "[2/5] Очищаем Python cache..."
find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

echo "[3/5] Проверяем Python..."
./venv/bin/python -c "
from backend.database.db import init_db
from backend.services.guest_service import GuestService
from backend.services.auth_service import AuthService
from backend.services.cabinet_service import CabinetService
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

echo "[4/5] Перезапускаем PM2..."
pm2 delete songforge 2>/dev/null || true
pm2 start app.py --name songforge --interpreter ./venv/bin/python --cwd "$DIR"
pm2 save

echo "[5/5] Проверяем health..."
sleep 3
HEALTH="$(curl -s http://127.0.0.1:8000/api/health)"
echo "$HEALTH"
if ! echo "$HEALTH" | grep -q "\"version\":\"$EXPECTED_VERSION\""; then
  echo "ОШИБКА: ожидалась версия $EXPECTED_VERSION"
  pm2 logs songforge --lines 30 --nostream
  exit 1
fi
echo ""
echo "=== Готово! Откройте http://195.19.20.245:8000/ ==="