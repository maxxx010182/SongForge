#!/bin/bash
# Принудительное обновление: скачать свежие файлы через GitHub API + перезапуск
set -e
DIR="${HOME}/SongForge"
GH_API="https://api.github.com/repos/maxxx010182/SongForge/contents"
EXPECTED_VERSION="2.9.31"

mkdir -p "$DIR/backend" "$DIR/assets"
cd "$DIR"

gh_get() {
  local out="$1"
  local repo_path="$2"
  curl -fsSL -H "Accept: application/vnd.github.raw" \
    "${GH_API}/${repo_path}?ref=main" \
    -o "$out"
  sed -i 's/\r$//' "$out" 2>/dev/null || true
  if [ ! -s "$out" ]; then
    echo "ОШИБКА: пустой файл $out"
    exit 1
  fi
}

free_port_8000() {
  pm2 delete songforge 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    if command -v fuser >/dev/null 2>&1; then
      fuser -k 8000/tcp 2>/dev/null || true
    fi
    if command -v lsof >/dev/null 2>&1; then
      for pid in $(lsof -t -i:8000 2>/dev/null); do
        kill -9 "$pid" 2>/dev/null || true
      done
    fi
    pkill -9 -f "${DIR}/app.py" 2>/dev/null || true
    sleep 1
    if ! (ss -lptn 'sport = :8000' 2>/dev/null | grep -q ':8000'); then
      return 0
    fi
  done
  return 1
}

echo "=== SongForge force-update v$EXPECTED_VERSION ==="

echo "[1/5] Скачиваем backend/app.py и index.html..."
gh_get backend/app.py backend/app.py
gh_get index.html index.html
gh_get app.py app.py

echo "[2/5] Проверка файлов на диске:"
grep 'version' backend/app.py | head -2
if ! grep -q "$EXPECTED_VERSION" backend/app.py; then
  echo "ОШИБКА: на диске не версия $EXPECTED_VERSION"
  exit 1
fi
if ! grep -q 'headerBrand' index.html; then
  echo "ОШИБКА: index.html не содержит headerBrand"
  exit 1
fi
echo "  index.html: $(wc -c < index.html) байт — OK"

echo "[3/5] Чистим Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

echo "[4/5] Перезапуск..."
if ! free_port_8000; then
  echo "ОШИБКА: порт 8000 занят"
  ss -lptn 'sport = :8000' 2>/dev/null || true
  exit 1
fi
pm2 start app.py --name songforge --interpreter ./venv/bin/python --cwd "$DIR"
pm2 save

echo "[5/5] Health check..."
sleep 4
HEALTH="$(curl -s http://127.0.0.1:8000/api/health)"
echo "$HEALTH"
if ! echo "$HEALTH" | grep -q "\"version\":\"$EXPECTED_VERSION\""; then
  echo ""
  echo "ОШИБКА: ожидалась $EXPECTED_VERSION"
  pm2 logs songforge --lines 15 --nostream
  exit 1
fi

echo ""
echo "=== Готово! v$EXPECTED_VERSION ==="