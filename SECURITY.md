# 安全说明

- `.env`、数据库密码、Bot Token、Fernet 密钥和备份严禁提交。
- Bot 容器使用非 root 用户、只读根文件系统、`cap_drop: ALL` 和 `no-new-privileges`。
- PostgreSQL 只加入 Compose 内部网络，不发布端口。
- 外部妙妙屋 X 查询必须使用只读账号；查询失败时绝不把失败当作未绑定，也不自动移除成员。
- 生产环境先保持 dry-run，管理员审阅审计日志后再启用移除。
- SSH 账号不得是 root，不授予 sudo，不允许执行任意命令。
- 真实部署前请轮换所有示例密钥，并限制服务器防火墙和 Docker 管理权限。
