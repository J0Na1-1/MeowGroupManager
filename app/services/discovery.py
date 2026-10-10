from __future__ import annotations

import asyncio
from dataclasses import dataclass
import shlex

import asyncssh


@dataclass(frozen=True)
class DatabaseDiscovery:
    kind: str
    path: str = "-"
    host: str = "-"
    port: str = "-"
    evidence: str = ""


class DiscoveryError(RuntimeError):
    pass


async def discover_database(
    host: str,
    username: str,
    password: str,
    port: int = 22,
    deployment: str = "docker",
) -> DatabaseDiscovery:
    """Open one read-only SSH session and return auditable evidence."""
    probe = (
        "printf 'TG_GUARD_SSH_OK\\n'; "
        "printf 'user='; id -un 2>/dev/null || true; "
        "printf 'host='; hostname 2>/dev/null || true; "
        "printf 'kernel='; uname -sr 2>/dev/null || true; "
        "printf 'psql='; command -v psql 2>/dev/null || true; "
        "printf 'mysql='; command -v mysql 2>/dev/null || true; "
        "printf 'sqlite3='; command -v sqlite3 2>/dev/null || true; "
        "printf 'files='; "
        "for f in /opt/*/*.db /opt/*/data/*.db /var/lib/*/*.db; do "
        "[ -f \"$f\" ] && printf '%s,' \"$f\"; done; printf '\\n'; "
        "printf 'docker='; command -v docker 2>/dev/null || true; "
        "docker ps --format '{{.Names}} {{.Image}}' 2>/dev/null || true; "
    )
    try:
        async with asyncssh.connect(
            host,
            port=port,
            username=username,
            password=password,
            known_hosts=None,
            login_timeout=15,
        ) as connection:
            result = await asyncio.wait_for(connection.run(probe, check=False), timeout=20)
    except Exception as exc:
        raise DiscoveryError(f"SSH 连接失败：{type(exc).__name__}") from exc

    output = result.stdout or ""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if "TG_GUARD_SSH_OK" not in lines:
        raise DiscoveryError("SSH 已连接但主控未返回验证标记")
    evidence = "；".join(lines[:16])
    lower = output.lower()
    docker_lines = [line for line in lines if "postgres" in line.lower() or "mysql" in line.lower()]
    if deployment == "docker" and any("postgres" in line.lower() for line in docker_lines):
        return DatabaseDiscovery("postgresql", "-", host, "5432", evidence)
    if deployment == "docker" and any("mysql" in line.lower() for line in docker_lines):
        return DatabaseDiscovery("mysql", "-", host, "3306", evidence)
    files = [line.split("=", 1)[1] for line in lines if line.startswith("files=/") and ".db" in line]
    if files:
        return DatabaseDiscovery("sqlite", files[0].split(",", 1)[0], "-", "-", evidence)
    if "psql=/" in lower:
        return DatabaseDiscovery("postgresql", "-", host, "5432", evidence)
    if "mysql=/" in lower:
        return DatabaseDiscovery("mysql", "-", host, "3306", evidence)
    if "sqlite3=/" in lower:
        return DatabaseDiscovery("sqlite", "-", "-", "-", evidence)
    raise DiscoveryError("SSH 已验证，但未识别数据库；请检查部署方式和只读账号权限")


async def discover_user_table(data: dict[str, str]) -> str:
    """List tables through the remote host using read-only SQL metadata queries."""
    host, username, password = data["ssh_host"], data["ssh_user"], data["ssh_password"]
    port, kind = int(data["ssh_port"]), data.get("db_type", "postgresql")
    db_name, db_user, db_password = data.get("db_name", "mmwx"), data.get("db_user", "mmwx"), data.get("db_password", "mmwx")
    if kind == "sqlite":
        command = f"sqlite3 {shlex.quote(data.get('db_path', '-'))} '.tables' 2>/dev/null || true"
    elif kind == "postgresql" and data.get("deployment") == "docker":
        # Query the MiMiaoWu PostgreSQL container, not the guard bot's database
        # or an unrelated PostgreSQL service such as remnawave-db.
        command = (
            "container=$(docker ps --format '{{.Names}} {{.Image}}' | "
            "awk 'tolower($1) ~ /miaomiaowux/ && tolower($2) ~ /postgres/ {print $1; exit}'); "
            "if [ -z \"$container\" ]; then "
            "container=$(docker ps --format '{{.Names}} {{.Image}}' | "
            "awk 'tolower($2) ~ /postgres:18-alpine/ {print $1; exit}'); fi; "
            "if [ -z \"$container\" ]; then printf 'TG_GUARD_NO_MMWX_POSTGRES\\n'; "
            "else docker exec \"$container\" psql -U mmwx -d mmwx -Atc "
            "\"SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public' ORDER BY tablename;\"; fi"
        )
    elif kind == "postgresql":
        command = f"PGPASSWORD={shlex.quote(db_password)} psql -h 127.0.0.1 -p 5432 -U {shlex.quote(db_user)} -d {shlex.quote(db_name)} -Atc \"SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public' ORDER BY tablename;\" 2>/dev/null || true"
    elif kind == "mysql":
        command = f"mysql --batch --skip-column-names -h 127.0.0.1 -P 3306 -u {shlex.quote(db_user)} -p{shlex.quote(db_password)} {shlex.quote(db_name)} -e 'SHOW TABLES' 2>/dev/null || true"
    else:
        return "未识别"
    try:
        async with asyncssh.connect(host, port=port, username=username, password=password, known_hosts=None, login_timeout=15) as connection:
            result = await asyncio.wait_for(connection.run(command, check=False), timeout=20)
    except Exception as exc:
        raise DiscoveryError(f"数据库表名查询失败：{type(exc).__name__}") from exc
    candidates = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    if "TG_GUARD_NO_MMWX_POSTGRES" in candidates:
        raise DiscoveryError("未找到妙妙屋 X PostgreSQL 容器")
    # MiMiaoWu X's user master table is known by schema evidence. Never
    # select traffic/baseline tables merely because their name contains user.
    if "users" in {name.split(".")[-1] for name in candidates}:
        return "users"
    for name in candidates:
        if name.lower() in {"accounts", "members"}:
            return name
    return "未识别"
