#!/bin/bash
# Первый раз: выложить ленд на podarok.sozdaipesnu.ru + HTTPS.
# Повторно: обновить файлы. Студию не трогает.
set -e

DIR="${HOME}/SongForge"
DEST="/var/www/podarok"
DOMAIN="podarok.sozdaipesnu.ru"
CONF_SRC="$DIR/scripts/nginx-podarok.conf"
EXPECTED_IP="195.19.20.245"
MAIL="support@sozdaipesnu.ru"

if [ "$(id -u)" -ne 0 ]; then
  echo "Запускайте от root (ssh root@195.19.20.245)"
  exit 1
fi
if [ ! -f "$DIR/landing/index.html" ]; then
  echo "Нет $DIR/landing/index.html — сначала update-now.sh"
  exit 1
fi
if [ ! -f "$CONF_SRC" ]; then
  echo "Нет $CONF_SRC"
  exit 1
fi

echo "=== Файлы ленда → $DEST ==="
mkdir -p "$DEST"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude 'README.txt' "$DIR/landing/" "$DEST/"
else
  find "$DEST" -mindepth 1 -delete
  cp -a "$DIR/landing/." "$DEST/"
  rm -f "$DEST/README.txt"
fi
chown -R www-data:www-data "$DEST" 2>/dev/null || chown -R nginx:nginx "$DEST" 2>/dev/null || true

echo "=== nginx ==="
if [ -d /etc/nginx/sites-available ]; then
  cp "$CONF_SRC" /etc/nginx/sites-available/podarok
  ln -sfn /etc/nginx/sites-available/podarok /etc/nginx/sites-enabled/podarok
else
  cp "$CONF_SRC" /etc/nginx/conf.d/podarok.conf
fi
nginx -t
systemctl reload nginx

echo "=== DNS ==="
RESOLVED="$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1; exit}')"
if [ -z "$RESOLVED" ]; then
  RESOLVED="$(python3 -c "import socket; print(socket.getaddrinfo('$DOMAIN', 80, socket.AF_INET)[0][4][0])" 2>/dev/null || true)"
fi
echo "  $DOMAIN → ${RESOLVED:-не резолвится}"
if [ "$RESOLVED" != "$EXPECTED_IP" ]; then
  echo "DNS ещё не смотрит на $EXPECTED_IP. Файлы и nginx уже на месте."
  echo "Подождите 15–60 мин и запустите этот скрипт ещё раз — допишет HTTPS."
  echo "Проверка с ПК: nslookup $DOMAIN"
  exit 0
fi

echo "=== HTTPS (certbot) ==="
if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
  echo "  сертификат уже есть"
else
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --redirect -m "$MAIL"
fi

echo ""
echo "Готово: https://$DOMAIN"
curl -sI "https://$DOMAIN" | head -5 || true
