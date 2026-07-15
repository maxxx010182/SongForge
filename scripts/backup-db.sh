#!/usr/bin/env bash
# Ежедневный бэкап SQLite SongForge (бета / прод).
# Cron пример (раз в сутки в 03:15):
#   15 3 * * * /root/SongForge/scripts/backup-db.sh >> /var/log/songforge-backup.log 2>&1
set -euo pipefail

ROOT="${SONGFORGE_ROOT:-$HOME/SongForge}"
DB="${ROOT}/data/songforge.db"
BACKUP_DIR="${SONGFORGE_BACKUP_DIR:-$HOME/backups/songforge}"
KEEP="${SONGFORGE_BACKUP_KEEP:-14}"

if [[ ! -f "$DB" ]]; then
  echo "backup-db: DB not found: $DB" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="${BACKUP_DIR}/songforge_${STAMP}.db"

if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB" ".backup '${OUT}'"
else
  cp -a "$DB" "$OUT"
fi

# Ротация: оставить последние KEEP файлов
mapfile -t FILES < <(ls -1t "${BACKUP_DIR}"/songforge_*.db 2>/dev/null || true)
if ((${#FILES[@]} > KEEP)); then
  for f in "${FILES[@]:KEEP}"; do
    rm -f -- "$f"
  done
fi

echo "backup-db: OK $(date -Iseconds) -> $OUT (keep=$KEEP)"
