#!/bin/bash
# Одна команда для обновления SongForge на VPS до последней версии с GitHub
set -e
DIR="${HOME}/SongForge"
mkdir -p "$DIR/scripts"
cd "$DIR"

echo "=== SongForge: скачиваем свежий deploy-скрипт ==="
CACHE_BUST="?$(date +%s)"
curl -fsSL \
  "https://raw.githubusercontent.com/maxxx010182/SongForge/main/scripts/deploy-vps.sh${CACHE_BUST}" \
  -o scripts/deploy-vps.sh \
  || curl -fsSL -H "Accept: application/vnd.github.raw" \
    "https://api.github.com/repos/maxxx010182/SongForge/contents/scripts/deploy-vps.sh?ref=main" \
    -o scripts/deploy-vps.sh
sed -i 's/\r$//' scripts/deploy-vps.sh 2>/dev/null || true
chmod +x scripts/deploy-vps.sh

echo "=== Запускаем деплой ==="
bash scripts/deploy-vps.sh