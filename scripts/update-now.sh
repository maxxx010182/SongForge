#!/bin/bash
# Одна команда для обновления SongForge на VPS до последней версии с GitHub
set -e
DIR="${HOME}/SongForge"
ARCHIVE_URL="https://codeload.github.com/maxxx010182/SongForge/tar.gz/main"
mkdir -p "$DIR/scripts"
cd "$DIR"

echo "=== SongForge: скачиваем свежий deploy-скрипт (tarball, без CDN-кэша) ==="
TMP=$(mktemp -d)
ARCHIVE="$TMP/repo.tar.gz"
BUST="?$(date +%s)"
if ! curl -fsSL "${ARCHIVE_URL}${BUST}" -o "$ARCHIVE"; then
  echo "ОШИБКА: не удалось скачать архив репозитория"
  rm -rf "$TMP"
  exit 1
fi
tar -xzf "$ARCHIVE" -C "$TMP"
SRC=$(find "$TMP" -maxdepth 1 -type d -name 'SongForge-*' | head -1)
if [ -z "$SRC" ] || [ ! -f "$SRC/scripts/deploy-vps.sh" ]; then
  echo "ОШИБКА: в архиве нет scripts/deploy-vps.sh"
  rm -rf "$TMP"
  exit 1
fi
cp "$SRC/scripts/deploy-vps.sh" scripts/deploy-vps.sh
sed -i 's/\r$//' scripts/deploy-vps.sh 2>/dev/null || true
chmod +x scripts/deploy-vps.sh
rm -rf "$TMP"

DEPLOY_VER=$(sed -n 's/.*deploy-script-version: *//p' scripts/deploy-vps.sh | head -1 | tr -d '\r')
if [ -z "$DEPLOY_VER" ]; then
  echo "ОШИБКА: в deploy-vps.sh нет маркера deploy-script-version"
  exit 1
fi
echo "  deploy-vps.sh: версия $DEPLOY_VER — OK"

echo "=== Запускаем деплой ==="
bash scripts/deploy-vps.sh