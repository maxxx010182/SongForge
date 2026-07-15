#!/bin/bash
# Деплой из архива на сервере (без GitHub). Архив: /tmp/songforge-update.tar.gz
set -e

DIR="${HOME}/SongForge"
ARCHIVE="${1:-/tmp/songforge-update.tar.gz}"
EXPECTED_VERSION="2.11.23"

strip_crlf() {
  local f="$1"
  [ -f "$f" ] || return 0
  sed -i 's/\r$//' "$f" 2>/dev/null || true
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
  echo "  Создаём venv..."
  rm -rf venv
  python3 -m venv venv
  ./venv/bin/pip install -q --upgrade pip
  ./venv/bin/pip install -q -r requirements.txt
}

echo "=== SongForge deploy-local (без GitHub) ==="
if [ ! -f "$ARCHIVE" ]; then
  echo "ОШИБКА: нет файла $ARCHIVE"
  echo "Сначала загрузите архив с Windows: scp ... root@server:/tmp/songforge-update.tar.gz"
  exit 1
fi

mkdir -p "$DIR"
cd "$DIR"

TMP=$(mktemp -d)
tar -xzf "$ARCHIVE" -C "$TMP" 2>/dev/null || tar -xzf "$ARCHIVE" -C "$TMP"
APP_PY=$(find "$TMP" -type f -path '*/backend/app.py' 2>/dev/null | head -1)
if [ -n "$APP_PY" ]; then
  SRC=$(dirname "$(dirname "$APP_PY")")
else
  SRC=$(find "$TMP" -maxdepth 3 -type d -name 'SongForge' 2>/dev/null | head -1)
fi
if [ -z "$SRC" ] || [ ! -f "$SRC/backend/app.py" ]; then
  echo "ОШИБКА: в архиве нет backend/app.py"
  echo "Содержимое архива:"
  find "$TMP" -maxdepth 3 -type d 2>/dev/null | head -20
  rm -rf "$TMP"
  exit 1
fi

echo "[1/6] Копируем файлы из архива..."
sync_from_src "$SRC" "$DIR"
find "$DIR/scripts" -name '*.sh' -exec strip_crlf {} \; 2>/dev/null || true
rm -rf "$TMP"

echo "[2/6] Зависимости..."
ensure_venv
./venv/bin/pip install -q -r requirements.txt 2>/dev/null || ./venv/bin/pip install -r requirements.txt

echo "[3/6] Проверка версии..."
if ! grep -qF "$EXPECTED_VERSION" backend/app.py; then
  echo "ОШИБКА: в архиве не версия $EXPECTED_VERSION"
  grep version backend/app.py | head -2 || true
  exit 1
fi

echo "[4/6] Перезапуск PM2..."
pm2 delete songforge 2>/dev/null || true
pm2 delete songforge-worker 2>/dev/null || true
sleep 1
pm2 start app.py --name songforge --interpreter ./venv/bin/python --cwd "$DIR"
pm2 start worker.py --name songforge-worker --interpreter ./venv/bin/python --cwd "$DIR"
pm2 save

echo "[5/6] Health..."
sleep 4
curl -s http://127.0.0.1:8000/api/health
echo ""
echo "=== Готово! v$EXPECTED_VERSION ==="