# 单元测试 + 覆盖率
pytest tests/unit --cov=src --cov-report=html --cov-report=term -o junit_family=xunit --junitxml=reports/junit.xml

# PBT
pytest tests/property

# 契约测试（需要启动 pact broker 或 mock）
pytest tests/contract

# 集成测试（会启动 testcontainers）
pytest tests/integration

# E2E（需要前端和所有服务运行）
npx playwright test tests/e2e --reporter=html

# 性能测试
k6 run tests/perf/reservation_load.js --out json=reports/k6.json

# 安全测试
bash tests/security/zap_scan.sh

# 可访问性测试
bash tests/a11y/run_a11y.sh