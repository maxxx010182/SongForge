#!/bin/bash
# SongForge — обновление на VPS (без git)
# Запуск: bash scripts/deploy-vps.sh

set -e

BASE="https://raw.githubusercontent.com/maxxx010182/SongForge/main"
DIR="${HOME}/SongForge"

echo "=== SongForge deploy ==="
cd "$DIR" || { echo "Папка $DIR не найдена!"; exit 1; }

mkdir -p backend/services backend/utils backend/database scripts

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
wget -q -O backend/services/yandex_client.py "$BASE/backend/services/yandex_client.py"
wget -q -O backend/services/history.py "$BASE/backend/services/history.py"
wget -q -O backend/services/consultant.py "$BASE/backend/services/consultant.py"

echo "[2/4] Проверяем Python..."
./venv/bin/python -c "
from backend.services.reference_translator import ReferenceTranslator
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