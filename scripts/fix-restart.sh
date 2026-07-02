#!/bin/bash
# Экстренный перезапуск SongForge (если деплой скачал файлы, но старый процесс не умер)
set -e
DIR="${HOME}/SongForge"
cd "$DIR"

echo "=== SongForge: принудительный перезапуск ==="

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
  pkill -9 -f "uvicorn.*8000" 2>/dev/null || true
  pkill -9 -f "${DIR}/app.py" 2>/dev/null || true
  sleep 1
  if ! (ss -lptn 'sport = :8000' 2>/dev/null | grep -q ':8000'); then
    break
  fi
done

pm2 start app.py --name songforge --interpreter ./venv/bin/python --cwd "$DIR"
pm2 save
sleep 3
curl -s http://127.0.0.1:8000/api/health
echo ""
echo "=== Готово ==="