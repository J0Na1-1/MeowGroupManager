#!/usr/bin/env bash
set -euo pipefail
chmod +x scripts/*.sh
python -m compileall -q app tests migrations
python - <<'PY'
from pathlib import Path
for name in ('docker-compose.yml','docker-compose.prod.yml'):
    s=Path(name).read_text()
    assert 'privileged:' not in s and 'network_mode:' not in s and '/var/run/docker.sock' not in s
print('compile and container hardening checks passed')
PY
