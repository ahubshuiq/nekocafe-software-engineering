# NekoCafe Smart Dining Reservation Platform

猫咖智慧餐饮预约平台 — 支持桌位时段预约、会员积分等级管理的微服务应用。

## 前置依赖

| 依赖 | 最低版本 | 用途 |
|------|---------|------|
| Docker Desktop | 24+ | 容器运行时（含 Compose V2） |
| Make | 任意版本 | `make` 快捷命令（可选，亦可直接用 `docker compose`） |
| Git | 2.30+ | 克隆仓库（如从远程获取） |

本地仅运行不改代码时，**只需 Docker**。Python 3.12 和 Node.js 20 仅在 `make test` 本地跑单测时需要。

## 一键启动

```bash
# 方式一：make（推荐）
make up

# 方式二：docker compose 直接执行
docker compose up -d --build
```

首次启动约需 1–2 分钟拉取镜像并构建，之后秒启。

## 验证

```bash
# 1. 健康检查 — 预约服务
curl http://localhost:8000/health
# 期望返回：
# {"status":"UP","service":"reservation-service","timestamp":"2026-..."}

# 2. 健康检查 — 会员服务
curl http://localhost:3000/health
# 期望返回：
# {"status":"UP","service":"member-service","timestamp":"2026-..."}

# 3. 查看容器状态
docker compose ps
# 所有服务状态应为 running（healthy）
```

## 服务端点

| 服务 | URL | 端口 |
|------|-----|------|
| Reservation（桌位预约） | http://localhost:8000 | 8000 |
| Member（会员） | http://localhost:3000 | 3000 |
| PostgreSQL | localhost:5432 | 5432 |
| Redis | localhost:6379 | 6379 |

API 文档（Swagger UI）：`http://localhost:8000/docs`

## 停止与清理

```bash
# 停止服务（保留数据卷）
make down
# 或：docker compose down -v

# 彻底清理（删除容器 + 数据卷）
docker compose down -v --remove-orphans

# 清理构建镜像
docker image prune -f
```

## 回滚

详见 [docs/rollback.md](docs/rollback.md)。

```bash
# Docker Compose 环境：修改 docker-compose.yml 中的镜像 tag 后重新启动
docker compose down
docker compose up -d

# K8s / Helm 环境：
helm rollback nekocafe <revision> -n nekocafe-prod --wait --timeout 5m
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 预约服务 | Python 3.12 + FastAPI + SQLAlchemy |
| 会员服务 | Node.js 20 + Express + pg |
| 数据库 | PostgreSQL 16 |
| 缓存 | Redis 7 |
| CI/CD | GitHub Actions（Lint → Test → SAST → Build → Scan → Push → CD） |

## 项目结构

```
.github/workflows/   CI/CD 流水线配置
docs/                 运维手册与回滚手册
services/reservation/ 桌位预约服务（Python）
services/member/      会员服务（Node.js）
infra/                数据库初始化脚本
docker-compose.yml    本地一键起栈
Makefile              常用命令封装
```
