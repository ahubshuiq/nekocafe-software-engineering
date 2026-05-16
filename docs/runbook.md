# NekoCafé 运维手册 (Runbook)

## 常用命令

### 本地一键启动
```bash
docker compose up -d --build
```

### 验证服务
```bash
curl http://localhost:8000/health   # 预约服务
curl http://localhost:3000/health   # 会员服务
```

### 查看日志
```bash
docker compose logs -f reservation
docker compose logs -f member
```

### 停止服务
```bash
docker compose down -v
```

## 故障排查

### 服务无响应
1. `docker compose ps` — 检查容器状态
2. `docker compose logs <service>` — 查看错误日志
3. `curl http://localhost:<port>/health` — 健康检查

### 数据库连接失败
1. 确认 postgres 容器运行中：`docker compose ps postgres`
2. 测试连接：`docker compose exec postgres psql -U nekocafe -l`
3. 检查 DATABASE_URL 环境变量是否正确

### Redis 连接失败
1. 确认 redis 容器运行中：`docker compose ps redis`
2. 测试连接：`docker compose exec redis redis-cli ping`

### 镜像构建失败
1. 清理 Docker 缓存：`docker compose build --no-cache`
2. 检查 Dockerfile 语法：`hadolint services/reservation/Dockerfile`
```
