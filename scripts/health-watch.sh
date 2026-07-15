#!/usr/bin/env bash
# Проверка /api/health. При падении — строка в лог (подключите Telegram сами при необходимости).
# Cron каждые 5 мин:
#   */5 * * * * /root/SongForge/scripts/health-watch.sh >> /var/log/songforge-health.log 2>&1
set -euo pipefail

URL="${SONGFORGE_HEALTH_URL:-https://sozdaipesnu.ru/api/health}"
STATE_FILE="${SONGFORGE_HEALTH_STATE:-/tmp/songforge-health-ok}"

code="$(curl -sS -o /tmp/songforge-health-body.json -w '%{http_code}' --max-time 15 "$URL" || echo 000)"
if [[ "$code" == "200" ]]; then
  if [[ -f "$STATE_FILE" ]] && [[ "$(cat "$STATE_FILE")" != "ok" ]]; then
    echo "health-watch: RECOVERED $(date -Iseconds) code=$code"
  fi
  echo ok >"$STATE_FILE"
  exit 0
fi

echo "health-watch: DOWN $(date -Iseconds) code=$code url=$URL body=$(head -c 200 /tmp/songforge-health-body.json 2>/dev/null || true)"
echo down >"$STATE_FILE"
exit 1
