/**
 * 性能测试 — k6 脚本
 * 对 /api/reservations 接口进行阶梯式负载测试
 *
 * 安装:   https://k6.io/docs/get-started/installation/
 * 运行:   k6 run tests/perf/reservation_load.js
 * 报告:   k6 run tests/perf/reservation_load.js --out json=tests/reports/k6.json
 * 前置:   docker compose up -d
 */

import http from "k6/http";
import { check, sleep } from "k6";

// ── 配置 ────────────────────────────────────────────────────

const BASE_URL = __ENV.RESERVATION_URL || "http://localhost:8000";

export const options = {
  // 阶梯式负载：ramp-up → 持续 → ramp-down
  stages: [
    { duration: "30s", target: 20 },   // 预热：30s 内升到 20 虚拟用户
    { duration: "1m",  target: 50 },   // 加压：1min 内升到 50 用户
    { duration: "1m",  target: 50 },   // 持续：50 用户维持 1min
    { duration: "30s", target: 0 },    // 收尾：30s 内降到 0
  ],

  // 阈值：P95 ≤ 350ms，错误率 < 0.5%
  thresholds: {
    http_req_duration: ["p(95)<350"],
    http_req_failed:   ["rate<0.005"],
  },
};

// ── 辅助函数 ────────────────────────────────────────────────

let counter = 0;

function uniquePayload() {
  counter++;
  const tableId = (counter % 5) + 1;
  const hour = 10 + (counter % 11);
  const futureDate = new Date();
  futureDate.setDate(futureDate.getDate() + 1);

  return JSON.stringify({
    member_id: Date.now() % 2_000_000_000 + counter,
    store_id: 1,
    table_id: tableId,
    reservation_date: futureDate.toISOString().slice(0, 10),
    start_time: `${String(hour).padStart(2, "0")}:00`,
    guest_count: 2,
  });
}

// ── 测试主函数 ──────────────────────────────────────────────

export default function () {
  const params = {
    headers: { "Content-Type": "application/json" },
  };

  // 1. 创建预约
  const createRes = http.post(
    `${BASE_URL}/api/reservations`,
    uniquePayload(),
    params
  );
  check(createRes, {
    "POST /api/reservations → 201": (r) => r.status === 201,
  });

  // 如果创建成功，查询 + 取消
  if (createRes.status === 201) {
    const rid = createRes.json("id");

    // 2. 查询预约
    const getRes = http.get(`${BASE_URL}/api/reservations/${rid}`);
    check(getRes, {
      "GET /api/reservations/:id → 200": (r) => r.status === 200,
    });

    // 3. 取消预约
    const delRes = http.del(`${BASE_URL}/api/reservations/${rid}`);
    check(delRes, {
      "DELETE /api/reservations/:id → 204": (r) => r.status === 204,
    });
  }

  // 4. 查询可用时段
  const futureDate = new Date();
  futureDate.setDate(futureDate.getDate() + 2);
  const slotsRes = http.get(
    `${BASE_URL}/api/reservations/available?store_id=1&reservation_date=${futureDate.toISOString().slice(0, 10)}&guest_count=2`
  );
  check(slotsRes, {
    "GET /api/reservations/available → 200": (r) => r.status === 200,
  });

  // 5. 健康检查
  const healthRes = http.get(`${BASE_URL}/health`);
  check(healthRes, {
    "GET /health → 200": (r) => r.status === 200,
  });

  sleep(1);
}
