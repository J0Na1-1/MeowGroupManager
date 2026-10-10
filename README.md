# TG Group Guard / MeowGroupManager

生产导向的 Telegram 群组新人验证、妙妙屋 X 绑定核验和成员清理机器人。

项目代号：`MeowGroupManager`

> 本项目目前按源码 + Docker Compose 部署。生产环境默认使用 `dry-run`，只有管理员在面板中明确选择“自动移出成员”后，才会执行移出操作。

## 功能概览

- 新成员进入超级群组后立即限制发言。
- 为新成员建立一次性、绑定 Telegram User ID 的验证记录。
- 私聊引导用户输入妙妙屋 X 用户名。
- 引导用户打开主控登录页面，在右上角生成 `/start <绑定码>` 命令。
- Bot 将用户提供的绑定码转换为官方 Telegram Bot 的 deep link。
- 支持在管理员面板中配置主控地址和 `Meow_bot` 用户名。
- `Meow_bot` 用户名强制要求以 `_bot` 结尾。
- 绑定完成后通过 SSH 只读查询妙妙屋 X `public.users.telegram_id`。
- 只有查询结果等于当前 Telegram User ID 时才解除群组限制。
- 支持 `dry-run`、仅查询不处理、自动移出成员三种运行模式。
- 自动移出采用 Telegram API 的“封禁后立即解除封禁”方式：用户被移出群组，但不会永久拉黑，可再次加入。
- 保护管理员、群主、机器人和查询失败对象。
- 管理员专属可视化面板：群组、运行模式、清理任务、被移除用户、SSH/数据库配置、审核记录和系统状态。
- SSH 和数据库连接参数加密保存，密码不显示在面板中。
- PostgreSQL 数据使用 Docker volume 持久化。
- Bot 容器使用非 root 用户、只读根文件系统、`cap_drop: ALL` 和 `no-new-privileges`。

## 工作流程

### 新人验证

```text
新人进入超级群组
  → Bot 收到 chat_member update
  → 写入 group_members 和 verifications
  → restrict_chat_member 限制发言
  → 群内发送“点击绑定 TG”按钮
  → 用户私聊 Bot
  → 输入妙妙屋 X 用户名
  → Bot 发送配置的主控 HTTPS 地址
  → 用户在页面右上角生成 /start 绑定命令
  → 用户把命令发给 TG Group Guard
  → Bot 生成官方 Meow_bot deep link
  → 用户完成官方绑定
  → 用户发送“我已完成绑定”
  → Bot SSH 只读查询 public.users.telegram_id
  → 匹配当前 Telegram User ID 后解除限制
```

### 超时处理

默认验证 token 有效期为 5 分钟。自动移出模式下，超时且未验证的成员会被移出群组；移出不会保留永久封禁。

### 定时核验

Bot 只处理已经通过入群事件记录的成员。Telegram Bot API 不能枚举全部历史普通成员，因此历史成员不会凭空出现在报告中。

查询失败与未绑定严格区分：

- 已绑定：保留；
- 未绑定：根据运行模式报告或移出；
- 查询失败：保留，不得自动移出。

## 前置条件

- Debian 12/13 或兼容 Linux；
- Git；
- Docker Engine；
- Docker Compose v1 `docker-compose` 或 Compose v2 `docker compose`；
- 一个 Telegram Bot Token；
- 一个超级群组；
- Bot 在群组中为管理员，并具备限制成员、封禁成员和邀请用户等必要权限；
- 妙妙屋 X 主控的非 root SSH 只读账号；
- 妙妙屋 X PostgreSQL 的只读查询凭证；
- 管理员 Telegram 数字 User ID。

不要使用 root SSH 账号，不要给查询账号 sudo，不要把密码、Token、私钥或数据库备份提交到 GitHub。

## 快速部署

### 1. 获取源码

```bash
git clone https://github.com/J0Na1-1/MeowGroupManager.git
cd MeowGroupManager
```

### 2. 创建环境文件

```bash
cp .env.example .env
chmod 600 .env
```

编辑 `.env`，至少填写：

```dotenv
TELEGRAM_BOT_TOKEN=从_BotFather_获取
DATABASE_URL=postgresql+asyncpg://bot:修改后的密码@postgres:5432/tg_guard
TOKEN_SECRET=至少32字节随机值
CONFIG_ENCRYPTION_KEY=有效的Fernet密钥
ADMIN_USER_IDS=你的Telegram数字UserID
POSTGRES_USER=bot
POSTGRES_DB=tg_guard
POSTGRES_PASSWORD=强随机数据库密码
```

生成密钥示例：

```bash
python3 - <<'PY'
import secrets
from cryptography.fernet import Fernet
print('TOKEN_SECRET=' + secrets.token_urlsafe(48))
print('CONFIG_ENCRYPTION_KEY=' + Fernet.generate_key().decode())
print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))
PY
```

不要把命令输出的密钥发到聊天或提交到 Git。

### 3. 安装、迁移和启动

本项目兼容当前服务器上的 `docker-compose` 命令：

```bash
bash scripts/install.sh
```

脚本会：

1. 检查 Docker 和 Compose；
2. 检查 `.env`；
3. 构建 Bot 镜像；
4. 启动 PostgreSQL；
5. 执行 Alembic 迁移；
6. 启动 Bot；
7. 执行健康检查。

查看状态：

```bash
docker-compose ps
docker-compose logs -f bot
```

如果服务器使用 Compose v2，可将命令替换为：

```bash
docker compose up -d --build
```

## Telegram 初始配置

### 1. 创建和设置 Bot

在 BotFather：

1. 创建 Bot；
2. 设置用户名；
3. 将 Bot 加入目标群组；
4. 将 Bot 设为管理员；
5. 开启限制成员、封禁成员、邀请用户等必要权限。

新人验证要求目标群组是超级群组。群组 ID 通常以 `-100` 开头。

### 2. 打开管理员面板

在目标群组发送：

```text
/admin
```

管理员面板只向 `.env` 中 `ADMIN_USER_IDS` 的用户开放。普通成员不能使用管理员面板，也不能执行配置操作。

### 3. 添加群组

点击：

```text
添加当前群组
```

Bot 会检查：

- 当前聊天是否为超级群组；
- 操作者是否为群组管理员或群主；
- Bot 是否为群组管理员。

添加后默认：

```text
新人验证：开启
运行模式：dry-run
```

### 4. 配置妙妙屋 X

点击：

```text
妙妙屋 X 配置
```

进入可视化配置面板：

```text
主控地址
部署方式
SSH 端口
SSH 只读用户
SSH 密码
数据库用户
数据库密码
Meow_bot
查看当前配置
开始连接配置
重新配置连接
返回主面板
```

配置规则：

- 主控地址可以填写 `abc.com`，系统会使用 `https://abc.com`；
- 也可以直接填写 `https://abc.com`，系统不会重复添加协议；
- 部署方式填写 `docker` 或 `script`；
- SSH 用户必须是非 root 只读账号；
- 数据库查询必须使用最小权限账号；
- SSH 密码和数据库密码会加密保存，不在面板回显；
- `Meow_bot` 请输入类似 `JonahMeow_bot` 或 `abc_bot` 的用户名；
- `Meow_bot` 必须以 `_bot` 结尾，否则保存失败。

当前已知妙妙屋 X Docker 数据库环境示例：

```text
容器：miaomiaowux-postgres
数据库：mmwx
用户：mmwx
用户表：public.users
绑定关系字段：public.users.telegram_id
```

### 5. 配置运行模式

点击：

```text
运行模式
```

可选：

```text
仅报告（dry-run）
仅查询不处理
自动移出成员
```

建议先使用：

```text
仅报告（dry-run）
```

确认报告、权限和绑定结果正确后，再明确选择：

```text
自动移出成员
```

### 6. 配置清理任务

点击：

```text
清理任务
```

可执行：

```text
开启任务
暂停任务
立即执行清理
查看查询报告
任务设置
返回主面板
```

## 用户绑定教程

用户在群组中被限制后：

1. 点击群内的“点击绑定 TG”；
2. 私聊 Bot 后发送妙妙屋 X 用户名；
3. Bot 返回管理员配置的主控地址，例如：

```text
https://abc.com
```

4. 打开页面，点击右上角头像；
5. 点击“生成绑定码”；
6. 复制页面生成的命令，例如：

```text
/start 436EFD726202
```

7. 将该命令发送给 TG Group Guard；
8. Bot 生成按钮并跳转配置的官方机器人，例如：

```text
https://t.me/xxx_bot?start=436EFD726202
```

9. 完成官方绑定；
10. 返回 TG Group Guard，发送：

```text
我已完成绑定
```

11. Bot 重新查询：

```sql
SELECT telegram_id
FROM public.users
WHERE username = '<用户名>';
```

只有 `telegram_id` 等于当前 Telegram User ID 时，Bot 才解除群组限制。

TG Group Guard 不自行计算绑定码，也不修改妙妙屋 X 数据库；用户从主控页面获取绑定命令，Bot 只负责转发到配置的官方 `Meow_bot`。

## 运维命令

```bash
# 查看服务
docker-compose ps

# 查看 Bot 日志
docker-compose logs -f bot

# 查看最近日志
docker-compose logs --tail=200 bot

# 健康检查
bash scripts/healthcheck.sh

# 备份
bash scripts/backup.sh

# 更新（会先备份）
bash scripts/update.sh

# 部署
bash scripts/deploy.sh
```

恢复数据库：

```bash
bash scripts/restore.sh backups/guard-YYYYMMDDTHHMMSSZ.sql.gz
```

恢复生产数据库前必须先备份，并确认目标数据库和备份文件。备份文件位于 `backups/`，不会提交到 Git。

## 目录结构

```text
MeowGroupManager/
├── app/
│   ├── db/                 # SQLAlchemy 模型
│   ├── handlers/           # 管理员面板和验证流程
│   └── services/           # SSH 探测、妙妙屋查询、Token、任务服务
├── migrations/             # Alembic 迁移
├── scripts/                # 安装、部署、更新、备份、恢复、健康检查
├── docker/
│   └── Dockerfile          # 非 root Bot 镜像
├── tests/
├── .env.example
├── docker-compose.yml
├── docker-compose.prod.yml
├── SECURITY.md
├── DEPLOY.md
└── TROUBLESHOOTING.md
```

## 安全边界

- 不提交 `.env`、Bot Token、SSH 密码、数据库密码、私钥、Fernet 密钥、备份和生产日志；
- Bot 不访问 Docker Socket；
- Bot 不使用 `privileged`、host network 或不必要 capabilities；
- PostgreSQL 不发布公网端口；
- Bot 通过 SSH 只读查询主控数据库；
- 外部数据库查询失败不能被当成未绑定；
- 查询失败不得触发自动移出；
- 管理员、群主、Bot 和白名单成员必须保护；
- Telegram Bot API 无法枚举所有普通历史成员；
- 不把完整绑定码写入日志；
- 不在聊天中发送密码、Token 或私钥；
- 生产环境启用自动移出前必须先审阅 dry-run 报告。

## 测试和验证

本地编译检查：

```bash
python3 -m py_compile app/main.py app/handlers/admin.py app/handlers/verification.py
```

安装测试依赖并执行：

```bash
python3 -m pip install -e '.[test]'
pytest -q
```

Docker 验证：

```bash
docker-compose build bot
docker-compose run --rm bot alembic upgrade head
docker-compose up -d bot
docker-compose ps
```

验收至少包括：

- Bot 和 PostgreSQL healthy；
- 超级群组新人能触发 chat_member；
- 新成员立即被限制发言；
- 私聊 `/start` 能进入绑定流程；
- `/start <绑定码>` 能生成官方 Bot 按钮；
- 绑定完成后能重新查询 `telegram_id`；
- 查询成功才解除限制；
- dry-run 不执行移出；
- 自动移出是移出后解除封禁，而非永久拉黑；
- 普通成员不能访问管理员面板。

## 已知限制

- 进程内超时任务在 Bot 重启后会丢失，生产环境应进一步改为数据库扫描任务；
- Telegram Bot API 不能枚举全部历史普通成员；
- 主控绑定命令由妙妙屋 X 主控生成，TG Group Guard 不复刻算法；
- 当前外部主控查询依赖配置的 SSH 只读路径；
- 完整生产验收仍需要在真实 Telegram 群组中执行一次新成员、绑定、解除限制和移出测试。

## 许可证

见 [LICENSE](LICENSE)。
