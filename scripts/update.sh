#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f .env || { echo '缺少 .env，未执行更新。' >&2; exit 1; }
bash scripts/backup.sh
git fetch --all --prune
git pull --ff-only
"${COMPOSE:-docker-compose}" build bot
"${COMPOSE:-docker-compose}" run --rm bot alembic upgrade head
"${COMPOSE:-docker-compose}" up -d
bash scripts/healthcheck.sh

