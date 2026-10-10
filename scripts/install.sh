#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo '缺少 Docker，请先安装。' >&2; exit 1; }
command -v docker-compose >/dev/null || { echo '缺少 Docker Compose，请安装 docker-compose 或 Compose v2。' >&2; exit 1; }
if [[ ! -f .env ]]; then cp .env.example .env; chmod 600 .env; echo '已创建 .env，请填写密钥后重新运行 install.sh。' >&2; exit 1; fi
mkdir -p backups logs
chmod 700 backups logs
export COMPOSE="${COMPOSE:-docker-compose}"
"$COMPOSE" build bot
"$COMPOSE" up -d postgres
"$COMPOSE" run --rm bot alembic upgrade head
"$COMPOSE" up -d bot
bash scripts/healthcheck.sh
printf '部署完成。请运行: %s logs -f bot\n' "$COMPOSE"

