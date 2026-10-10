#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f .env || { echo '缺少 .env。' >&2; exit 1; }
set -a; source .env; set +a
mkdir -p backups
file="backups/guard-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
"${COMPOSE:-docker-compose}" exec -T postgres pg_dump -U "${POSTGRES_USER:-bot}" -d "${POSTGRES_DB:-tg_guard}" | gzip > "$file"
find backups -type f -name '*.sql.gz' -mtime +"${BACKUP_RETENTION_DAYS:-14}" -delete
printf '备份已创建: %s\n' "$file"

