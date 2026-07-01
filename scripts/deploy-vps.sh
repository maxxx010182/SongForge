#!/bin/bash
# SongForge — обновление на VPS (без git)
# Запуск: bash scripts/deploy-vps.sh

set -e

BASE="https://raw.githubusercontent.com/maxxx010182/SongForge/main"
DIR="${HOME}/SongForge"

echo "=== SongForge deploy ==="
cd "$DIR" || { echo "Папка $DIR не найдена!"; exit 1; }

mkdir -p backend/services backend/utils backend/database scripts

echo "[0/4] Обновляем скрипт деплоя..."
wget -q -O scripts/deploy-vps.sh "$BASE/scripts/deploy-vps.sh"
chmod +x scripts/deploy-vps.sh

echo "[1/4] Скачиваем файлы с GitHub..."
wget -q -O index.html "$BASE/index.html"

wget -q -O backend/app.py "$BASE/backend/app.py"
wget -q -O backend/models.py "$BASE/backend/models.py"
wget -q -O backend/settings.py "$BASE/backend/settings.py"
wget -q -O backend/logger.py "$BASE/backend/logger.py"
wget -q -O backend/utils/text.py "$BASE/backend/utils/text.py"
wget -q -O backend/database/db.py "$BASE/backend/database/db.py"
wget -q -O backend/services/ai_producer.py "$BASE/backend/services/ai_producer.py"
wget -q -O backend/services/prompt_builder.py "$BASE/backend/services/prompt_builder.py"
wget -q -O backend/services/apipass_client.py "$BASE/backend/services/apipass_client.py"
wget -q -O backend/services/ai_music_analyst.py "$BASE/backend/services/ai_music_analyst.py"
wget -q -O backend/services/ai_prompt_composer.py "$BASE/backend/services/ai_prompt_composer.py"
wget -q -O backend/services/reference_translator.py "$BASE/backend/services/reference_translator.py"
wget -q -O backend/services/style_enforcer.py "$BASE/backend/services/style_enforcer.py"
wget -q -O backend/services/plan_overrides.py "$BASE/backend/services/plan_overrides.py"
wget -q -O backend/services/genre_resolver.py "$BASE/backend/services/genre_resolver.py"
wget -q -O backend/services/yandex_client.py "$BASE/backend/services/yandex_client.py"
wget -q -O backend/services/history.py "$BASE/backend/services/history.py"
wget -q -O backend/services/consultant.py "$BASE/backend/services/consultant.py"

for f in \
  backend/services/genre_resolver.py \
  backend/services/plan_overrides.py \
  backend/services/style_enforcer.py; do
  if [ ! -s "$f" ]; then
    echo "ОШИБКА: не скачан $f"
    exit 1
  fi
done

echo "[2/4] Проверяем Python..."
./venv/bin/python -c "
from backend.services.genre_resolver import resolve_genre
from backend.services.plan_overrides import apply_user_to_plan
from backend.services.style_enforcer import enforce_style
from backend.services.ai_music_analyst import AiMusicAnalyst
from backend.services.prompt_builder import PromptBuilder
print('import OK')
"

echo "[3/4] Перезапускаем PM2..."
pm2 restart songforge

echo "[4/4] Проверяем health..."
sleep 2
curl -s http://127.0.0.1:8000/api/health
echo ""
echo "=== Готово! Откройте http://195.19.20.245:8000/ ==="