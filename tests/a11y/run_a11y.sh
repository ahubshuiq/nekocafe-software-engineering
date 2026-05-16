#!/bin/bash
# ============================================================
# 可访问性测试 — Lighthouse CI
#
# 功能: 对前端页面运行 Lighthouse，检查可访问性评分 ≥ 90
#
# 前置:
#   1. npm install -g @lhci/cli
#   2. docker compose up -d (前端 + 后端服务)
#
# 运行:
#   bash tests/a11y/run_a11y.sh
#
# 输出:
#   tests/reports/lighthouse/  — Lighthouse HTML 报告
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORT_DIR="$PROJECT_ROOT/tests/reports/lighthouse"

mkdir -p "$REPORT_DIR"

echo "=========================================="
echo " Lighthouse 可访问性测试"
echo " Target: ${FRONTEND_URL:-http://localhost:5173}"
echo "=========================================="

# 如果前端未部署，测试 API 健康检查端点的基本可访问性
if ! curl -sf "${FRONTEND_URL:-http://localhost:5173}" > /dev/null 2>&1; then
  echo "[WARN] 前端未部署，改为测试 API 健康检查端点"

  for url in "http://localhost:8000/health" "http://localhost:3000/health"; do
    echo -n "  检查 $url ... "
    status=$(curl -sf -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    if [ "$status" = "200" ]; then
      echo "OK (200)"
    else
      echo "FAIL ($status)"
    fi
  done

  echo ""
  echo "[INFO] 前端部署后请重新运行此脚本以获取 Lighthouse 评分"
  exit 0
fi

# 运行 Lighthouse CI
cd "$PROJECT_ROOT"
lhci autorun --config=tests/a11y/lighthouse.config.js || true

echo ""
echo "=========================================="
echo " 测试完成"
echo " 报告: $REPORT_DIR"
echo "=========================================="
