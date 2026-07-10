#!/bin/bash
# Одна команда для обновления SongForge на VPS до последней версии с GitHub
set -e
DIR="${HOME}/SongForge"
REQUIRED_DEPLOY_VERSION="13"
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

if ! grep -q "deploy-script-version: $REQUIRED_DEPLOY_VERSION" scripts/deploy-vps.sh; then
  echo "ОШИБКА: на диске старый deploy-vps.sh (ожидалась версия $REQUIRED_DEPLOY_VERSION)"
  grep 'deploy-script-version' scripts/deploy-vps.sh || true
  exit 1
fi
echo "  deploy-vps.sh: версия $REQUIRED_DEPLOY_VERSION — OK"

echo "=== Запускаем деплой ==="
bash scripts/deploy-vps.sh