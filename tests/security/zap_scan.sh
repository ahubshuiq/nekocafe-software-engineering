#!/bin/bash
# ============================================================
# OWASP ZAP Baseline 安全扫描
#
# 功能：对预约服务进行自动化 Baseline 扫描，输出 HTML 报告。
#
# 前置：
#   1. Docker 已安装并运行
#   2. 预约服务运行在 http://localhost:8000
#
# 运行：
#   cd <项目根目录>
#   bash tests/security/zap_scan.sh
#
# 输出：
#   tests/reports/scan_report.html   — HTML 安全扫描报告
#   tests/reports/zap_baseline.log   — 扫描日志
# ============================================================

set -e

TARGET_URL="${TARGET_URL:-http://host.docker.internal:8000}"
REPORT_DIR="tests/reports"
REPORT_FILE="${REPORT_DIR}/scan_report.html"
LOG_FILE="${REPORT_DIR}/zap_baseline.log"

mkdir -p "${REPORT_DIR}"

echo "=========================================="
echo " OWASP ZAP Baseline Scan"
echo " Target: ${TARGET_URL}"
echo "=========================================="

# 使用 owasp/zap2docker-stable 镜像运行 baseline 扫描
# -t: 目标 URL
# -r: HTML 报告输出路径
# -w: 日志输出路径
# -l: 规则级别 (PASS, IGNORE, WARN, FAIL)
# -I: 不在有 WARN 时失败（只在 FAIL 时失败）
docker run --rm \
  -v "$(pwd):/zap/wrk/:rw" \
  -t owasp/zap2docker-stable:latest \
  zap-baseline.py \
    -t "${TARGET_URL}" \
    -r "/zap/wrk/${REPORT_FILE}" \
    -w "/zap/wrk/${LOG_FILE}" \
    -c "/zap/wrk/tests/security/zap-baseline.conf" \
    -l WARN \
    -I || true
    # || true: baseline 扫描可能返回非零退出码（发现警告/问题时不视为构建失败）

echo ""
echo "=========================================="
echo " 扫描完成"
echo " 报告: ${REPORT_FILE}"
echo " 日志: ${LOG_FILE}"
echo "=========================================="
