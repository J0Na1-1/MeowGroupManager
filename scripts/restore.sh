#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backup="${1:-}"
test -n "$backup" && test -f "$backup" || { echo '用法: restore.sh backups/backup.sql.gz' >&2; exit 2; }
if [[ "${CONFIRM_RESTORE:-}" != "YES" ]]; then
  echo '恢复会覆盖当前数据库。先在隔离环境测试；明确确认请设置 CONFIRM_RESTORE=YES。' >&2
  exit 1
fi
set -a; source .env; set +a
echo "目标数据库: ${POSTGRES_DB:-tg_guard} / 用户: ${POSTGRES_USER:-bot}"
gzip -dc "$backup" | "${COMPOSE:-docker-compose}" exec -T postgres psql -U "${POSTGRES_USER:-bot}" -d "${POSTGRES_DB:-tg_guard}"

