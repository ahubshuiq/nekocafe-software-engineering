# NekoCafe Smart Dining Reservation Platform

猫咖智慧餐饮预约平台 — 支持桌位时段预约、会员积分等级管理的微服务应用。

## 前置依赖

| 依赖 | 最低版本 | 用途 |
|------|---------|------|
| Docker Desktop | 24+ | 容器运行时（含 Compose V2） |
| Make | 任意版本 | `make` 快捷命令（可选，亦可直接用 `docker compose`） |
| Git | 2.30+ | 克隆仓库（如从远程获取） |
| Python | 3.12+ | 本地运行单元测试/变异测试 |
| Node.js | 20+ | 本地运行会员服务测试 |

## 一键启动

```bash
docker compose up -d --build
```

首次启动约需 1–2 分钟拉取镜像并构建，之后秒启。

## 验证

```bash
curl http://localhost:8000/health   # 预约服务
curl http://localhost:3000/health   # 会员服务
docker compose ps                   # 所有服务应为 running (healthy)
```

## 运行测试

```bash
# 单元测试 + 覆盖率
pytest tests/unit --cov=services/reservation/src --cov-report=term

# 基于属性的测试 (Hypothesis PBT)
pytest tests/property -v

# 集成测试 (Testcontainers，需 Docker)
pytest tests/integration -v

# E2E 测试 (Playwright)
npx playwright test tests/e2e/user_journey.spec.js

# 性能测试 (k6)
k6 run tests/perf/reservation_load.js

# 安全扫描 (OWASP ZAP)
bash tests/security/zap_scan.sh

# 变异测试
python tests/run_mutation.py
```

## 服务端点

| 服务 | URL | 端口 |
|------|-----|------|
| Reservation（桌位预约） | http://localhost:8000 | 8000 |
| Member（会员） | http://localhost:3000 | 3000 |
| PostgreSQL | localhost:5432 | 5432 |
| Redis | localhost:6379 | 6379 |

API 文档（Swagger UI）：`http://localhost:8000/docs`

## 项目结构

```
.github/workflows/         CI/CD 流水线 (ci.yml, cd.yml)
docker-compose.yml         本地开发环境
services/
  reservation/             Python FastAPI 预约服务
    src/main.py            API 端点 + 业务逻辑
    Dockerfile
  member/                  Node.js Express 会员服务
    src/index.js           API 端点 + 业务逻辑
    Dockerfile
infra/
  k8s/                     Kubernetes 清单 (Deployment, Service, PDB)
  helm/                    Helm Chart
  init-db.sql              数据库初始化脚本
tests/
  unit/                    单元测试 (26 条，86% 覆盖率)
  property/                基于属性的测试 (7 条 Hypothesis)
  contract/                Pact 契约测试 (2 对 consumer-provider)
  integration/             集成测试 Testcontainers (20 条)
  e2e/                     E2E 测试 Playwright (3 条用户旅程)
  perf/                    k6 负载测试脚本
  security/                OWASP ZAP 配置
  a11y/                    Lighthouse 可访问性配置
  reports/                 测试报告 (coverage, mutation, pact, junit)
  conftest.py              共享测试 fixtures
  run_mutation.py          自定义变异测试脚本
docs/                      文档与截图
```

## 停止与清理

```bash
docker compose down -v              # 停止并删除数据卷
docker compose down -v --remove-orphans  # 彻底清理
```

## 回滚

详见 [docs/rollback.md](docs/rollback.md)。

## 技术栈

| 组件 | 技术 |
|------|------|
| 预约服务 | Python 3.12 + FastAPI + SQLAlchemy |
| 会员服务 | Node.js 20 + Express + pg |
| 数据库 | PostgreSQL 16 |
| 缓存 | Redis 7 |
| CI/CD | GitHub Actions (Lint -> Test -> SAST -> Build -> Scan -> Push -> CD) |
