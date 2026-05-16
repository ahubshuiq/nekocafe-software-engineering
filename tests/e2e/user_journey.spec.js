/**
 * E2E 端到端测试 — Playwright API 测试模式（无浏览器）
 *
 * 使用 Playwright 的 request context 直接发 HTTP 请求，
 * 模拟 3 条完整用户旅程，不依赖前端页面。
 *
 * 安装:   npm init -y && npm i -D @playwright/test
 * 运行:   npx playwright test tests/e2e/user_journey.spec.js
 * 前置:   docker compose up -d  (预约服务运行在 localhost:8000)
 */

const { test, expect } = require("@playwright/test");

const BASE_URL = process.env.RESERVATION_URL || "http://localhost:8000";

// 生成唯一 member_id
function uid() {
  return Date.now() % 2_000_000_000 + Math.floor(Math.random() * 10000);
}

// 生成未来日期
function futureDate(daysAhead = 1) {
  const d = new Date();
  d.setDate(d.getDate() + daysAhead);
  return d.toISOString().slice(0, 10);
}

// ============================================================
// Journey 1: 新用户 → 查询可用时段 → 创建预约 → 查询详情 → 取消预约
// ============================================================

test.describe("Journey 1: 完整预约流程", () => {
  let reservationId;
  const memberId = uid();
  const resvDate = futureDate(1);

  test("查询可用时段", async ({ request }) => {
    const resp = await request.get(`${BASE_URL}/api/reservations/available`, {
      params: { store_id: 1, reservation_date: resvDate, guest_count: 2 },
    });
    expect(resp.status()).toBe(200);
    const slots = await resp.json();
    expect(slots.length).toBeGreaterThan(0);
    expect(slots[0]).toHaveProperty("table_id");
    expect(slots[0]).toHaveProperty("start_time");
  });

  test("创建预约", async ({ request }) => {
    const resp = await request.post(`${BASE_URL}/api/reservations`, {
      data: {
        member_id: memberId,
        store_id: 1,
        table_id: 1,
        reservation_date: resvDate,
        start_time: "18:00",
        guest_count: 2,
      },
    });
    expect(resp.status()).toBe(201);
    const body = await resp.json();
    expect(body.status).toBe("CONFIRMED");
    reservationId = body.id;
  });

  test("查询预约详情", async ({ request }) => {
    const resp = await request.get(
      `${BASE_URL}/api/reservations/${reservationId}`
    );
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.id).toBe(reservationId);
    expect(body.member_id).toBe(memberId);
    expect(body.status).toBe("CONFIRMED");
  });

  test("取消预约", async ({ request }) => {
    const resp = await request.delete(
      `${BASE_URL}/api/reservations/${reservationId}`
    );
    expect(resp.status()).toBe(204);
  });

  test("确认取消状态", async ({ request }) => {
    const resp = await request.get(
      `${BASE_URL}/api/reservations/${reservationId}`
    );
    expect(resp.status()).toBe(200);
    expect((await resp.json()).status).toBe("CANCELLED");
  });
});

// ============================================================
// Journey 2: 同一用户多次预约 → 部分取消 → 验证剩余状态
// ============================================================

test.describe("Journey 2: 多次预约与部分取消", () => {
  const memberId = uid();
  const resvDate = futureDate(2);
  const ids = [];

  test("创建 3 个不同桌位的预约", async ({ request }) => {
    for (const tableId of [1, 2, 3]) {
      const resp = await request.post(`${BASE_URL}/api/reservations`, {
        data: {
          member_id: memberId,
          store_id: 1,
          table_id: tableId,
          reservation_date: resvDate,
          start_time: "14:00",
          guest_count: 2,
        },
      });
      expect(resp.status()).toBe(201);
      ids.push((await resp.json()).id);
    }
  });

  test("取消第 2 个预约", async ({ request }) => {
    const resp = await request.delete(
      `${BASE_URL}/api/reservations/${ids[1]}`
    );
    expect(resp.status()).toBe(204);
  });

  test("其余预约仍为 CONFIRMED", async ({ request }) => {
    for (const rid of [ids[0], ids[2]]) {
      const resp = await request.get(
        `${BASE_URL}/api/reservations/${rid}`
      );
      expect((await resp.json()).status).toBe("CONFIRMED");
    }
  });
});

// ============================================================
// Journey 3: 冲突处理 — 同一时段重叠预约 → 改约其他桌位 → 取消后重新预约
// ============================================================

test.describe("Journey 3: 冲突与恢复", () => {
  const resvDate = futureDate(3);

  test("第一用户成功预约", async ({ request }) => {
    const resp = await request.post(`${BASE_URL}/api/reservations`, {
      data: {
        member_id: uid(),
        store_id: 1,
        table_id: 1,
        reservation_date: resvDate,
        start_time: "15:00",
        guest_count: 2,
      },
    });
    expect(resp.status()).toBe(201);
  });

  test("第二用户同桌位同时段返回 409", async ({ request }) => {
    const resp = await request.post(`${BASE_URL}/api/reservations`, {
      data: {
        member_id: uid(),
        store_id: 1,
        table_id: 1,
        reservation_date: resvDate,
        start_time: "15:00",
        guest_count: 2,
      },
    });
    expect(resp.status()).toBe(409);
  });

  test("第二用户改约其他桌位成功", async ({ request }) => {
    const resp = await request.post(`${BASE_URL}/api/reservations`, {
      data: {
        member_id: uid(),
        store_id: 1,
        table_id: 2,
        reservation_date: resvDate,
        start_time: "15:00",
        guest_count: 2,
      },
    });
    expect(resp.status()).toBe(201);
  });
});
