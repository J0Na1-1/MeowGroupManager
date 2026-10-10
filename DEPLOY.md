# 部署教程

1. 安装 Debian 12/13、Git、Docker 和 Docker Compose。
2. 克隆项目并复制 `.env.example` 为 `.env`，填写 Bot Token、随机 TOKEN_SECRET、Fernet 密钥和 PostgreSQL 密码。
3. 执行 `bash scripts/install.sh`。脚本会构建镜像、启动数据库、执行迁移、启动 Bot 和健康检查。
4. 在 BotFather 创建机器人，将机器人加入群组并授予限制成员、删除消息和邀请用户权限。
5. 使用管理员数字 Telegram User ID 配置管理员白名单。
6. 在管理面板配置妙妙屋 X 的非 root SSH 只读账号和数据库只读账号；密码只加密存储，面板不回显。
7. 先使用 dry-run 和手动检查验证查询结果，确认审计日志后再启用自动移除。

常用命令：

```bash
docker-compose ps
docker-compose logs -f bot
bash scripts/backup.sh
bash scripts/restore.sh backups/guard-YYYYMMDDTHHMMSSZ.sql.gz
bash scripts/update.sh
bash scripts/healthcheck.sh
```

恢复生产库前必须先备份并由管理员确认；建议先恢复到隔离测试项目验证备份完整性。
