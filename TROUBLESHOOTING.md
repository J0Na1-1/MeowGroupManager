# 故障排查

## 容器未启动

```bash
docker-compose ps
docker-compose logs --tail=100 bot postgres
```

确认 `.env` 存在、`TELEGRAM_BOT_TOKEN`、`POSTGRES_PASSWORD`、`TOKEN_SECRET` 和 `CONFIG_ENCRYPTION_KEY` 已填写。

## 数据库迁移失败

确认 PostgreSQL 健康后执行：

```bash
docker-compose run --rm bot alembic upgrade head
```

## Telegram 无响应

确认 Bot 已加入群组并拥有删除消息、限制成员和邀请用户权限；检查是否有另一个 polling 实例。

## 查询失败

查询失败不会触发自动移除。检查只读账号、SSH 网络、数据库路径和字段映射，并查看审计日志。
