#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker-compose >/dev/null || { echo '缺少 docker-compose。' >&2; exit 1; }
test -f .env || { echo '缺少 .env，未执行部署。' >&2; exit 1; }
source .env
bash scripts/backup.sh
"${COMPOSE:-docker-compose}" build bot
"${COMPOSE:-docker-compose}" run --rm bot alembic upgrade head
"${COMPOSE:-docker-compose}" up -d
bash scripts/healthcheck.sh

