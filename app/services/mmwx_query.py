from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass
from datetime import datetime

import asyncssh


@dataclass(frozen=True)
class MMwXUser:
    telegram_id: int
    username: str
    active: bool
    package_end_date: str | None


async def query_mmwx_users(data: dict[str, str], telegram_ids: list[int]) -> dict[int, MMwXUser]:
    """Read public.users by telegram_id over the configured SSH read-only path."""
    if not telegram_ids:
        return {}
    ids = ",".join(str(int(value)) for value in sorted(set(telegram_ids)))
    host, username, password = data["ssh_host"], data["ssh_user"], data["ssh_password"]
    port = int(data.get("ssh_port", 22))
    # Values are fixed/validated and no user data is selected beyond the fields needed by the report.
    sql = (
        "SELECT telegram_id, username, is_active, "
        "COALESCE(to_char(package_end_date, 'YYYY-MM-DD HH24:MI:SS'), '') "
        f"FROM public.users WHERE telegram_id IN ({ids});"
    )
    if data.get("deployment") == "docker":
        command = (
            "container=$(docker ps --format '{{.Names}} {{.Image}}' | "
            "awk 'tolower($1) ~ /miaomiaowux/ && tolower($2) ~ /postgres/ {print $1; exit}'); "
            "docker exec \"$container\" psql -U mmwx -d mmwx -AtF '|' -c "
            + shlex.quote(sql)
        )
    else:
        command = (
            f"PGPASSWORD={shlex.quote(data.get('db_password', ''))} psql -h 127.0.0.1 "
            f"-p {shlex.quote(data.get('db_port', '5432'))} -U {shlex.quote(data.get('db_user', 'mmwx'))} "
            f"-d {shlex.quote(data.get('db_name', 'mmwx'))} -AtF '|' -c {shlex.quote(sql)}"
        )
    try:
        async with asyncssh.connect(host, port=port, username=username, password=password, known_hosts=None, login_timeout=15) as connection:
            result = await asyncio.wait_for(connection.run(command, check=False), timeout=20)
    except Exception as exc:
        raise RuntimeError(f"妙妙屋 X 查询失败：{type(exc).__name__}") from exc
    if result.exit_status != 0:
        raise RuntimeError("妙妙屋 X 查询失败：数据库命令返回错误")
    users: dict[int, MMwXUser] = {}
    for line in (result.stdout or "").splitlines():
        parts = line.split("|", 3)
        if len(parts) != 4:
            continue
        try:
            tg_id = int(parts[0])
            users[tg_id] = MMwXUser(tg_id, parts[1], parts[2] in {"1", "t", "true"}, parts[3] or None)
        except ValueError:
            continue
    return users
