/**
 * E2E 端到端测试 — 3 条核心用户旅程
 *
 * 使用 Playwright 的 request context 直接发 HTTP 请求，
 * 模拟完整业务流程，覆盖预约服务 + 会员服务。
 *
 * 安装:   npm init -y && npm i -D @playwright/test
 * 运行:   npx playwright test tests/e2e/user_journey.spec.js
 * 前置:   docker compose up -d  (预约服务 :8000, 会员服务 :3000)
 */

const { test, expect } = require("@playwright/test");

const RESERVATION_URL = process.env.RESERVATION_URL || "http://localhost:8000";
const MEMBER_URL = process.env.MEMBER_URL || "http://localhost:3000";

// ── 辅助函数 ────────────────────────────────────────────────

function uid() {
  return Date.now() % 2_000_000_000 + Math.floor(Math.random() * 10000);
}

function futureDate(daysAhead = 1) {
  const d = new Date();
  d.setDate(d.getDate() + daysAhead);
  return d.toISOString().slice(0, 10);
}

function randomPhone() {
  const prefix = "138";
  const suffix = String(Math.floor(Math.random() * 1_0000_0000)).padStart(8, "0");
  return prefix + suffix;
}

// ============================================================
// Journey 1: 新用户注册 → 浏览门店 → 完成预约 → 取消预约
// ============================================================

test.describe("Journey 1: 新用户注册到预约全流程", () => {
  let memberId;
  let reservationId;
  const phone = randomPhone();
  const resvDate = futureDate(1);

  test("1.1 新用户注册", async ({ request }) => {
    const resp = await request.post(`${MEMBER_URL}/api/members`, {
      data: {
        name: "测试用户",
        phone: phone,
        email: "test@nekocafe.com",
        password: "TestPass1",
      },
    });
    expect(resp.status()).toBe(201);
    const body = await resp.json();
    expect(body.name).toBe("测试用户");
    expect(body.phone).toBe(phone);
    expect(body.level).toBe("NORMAL");
    expect(body.points).toBe(0);
    memberId = body.id;
  });

  test("1.2 查询会员信息确认注册成功", async ({ request }) => {
    const resp = await request.get(`${MEMBER_URL}/api/members/${memberId}`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.id).toBe(memberId);
    expect(body.phone).toBe(phone);
  });

  test("1.3 浏览门店 — 查询可用时段", async ({ request }) => {
    const resp = await request.get(`${RESERVATION_URL}/api/reservations/available`, {
      params: { store_id: 1, reservation_date: resvDate, guest_count: 2 },
    });
    expect(resp.status()).toBe(200);
    const slots = await resp.json();
    expect(slots.length).toBeGreaterThan(0);
    expect(slots[0]).toHaveProperty("table_id");
    expect(slots[0]).toHaveProperty("start_time");
    expect(slots[0]).toHaveProperty("zone");
  });

  test("1.4 完成预约", async ({ request }) => {
    const resp = await request.post(`${RESERVATION_URL}/api/reservations`, {
      data: {
        member_id: memberId,
        store_id: 1,
        table_id: 1,
        reservation_date: resvDate,
        start_time: "18:00",
        guest_count: 2,
        cat_preference: "橘猫",
      },
    });
    expect(resp.status()).toBe(201);
    const body = await resp.json();
    expect(body.status).toBe("CONFIRMED");
    expect(body.member_id).toBe(memberId);
    expect(body.cat_preference).toBe("橘猫");
    reservationId = body.id;
  });

  test("1.5 查询预约详情", async ({ request }) => {
    const resp = await request.get(`${RESERVATION_URL}/api/reservations/${reservationId}`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.id).toBe(reservationId);
    expect(body.member_id).toBe(memberId);
    expect(body.status).toBe("CONFIRMED");
  });

  test("1.6 取消预约", async ({ request }) => {
    const resp = await request.delete(`${RESERVATION_URL}/api/reservations/${reservationId}`);
    expect(resp.status()).toBe(204);
  });

  test("1.7 确认取消后状态为 CANCELLED", async ({ request }) => {
    const resp = await request.get(`${RESERVATION_URL}/api/reservations/${reservationId}`);
    expect(resp.status()).toBe(200);
    expect((await resp.json()).status).toBe("CANCELLED");
  });
});

// ============================================================
// Journey 2: 老会员登录 → 积分累加 → 查询积分 → 积分兑换
// (任务书要求: 登录 → AI 推荐 → 下单 → 支付 → 评价)
// 注: AI 推荐/下单/支付/评价为规划中功能，当前用积分流程替代验证会员核心能力
// ============================================================

test.describe("Journey 2: 老会员积分消费全流程", () => {
  let memberId;
  const phone = randomPhone();

  test("2.1 老会员注册（模拟已有账户）", async ({ request }) => {
    const resp = await request.post(`${MEMBER_URL}/api/members`, {
      data: { name: "老会员", phone, password: "OldPass1" },
    });
    expect(resp.status()).toBe(201);
    memberId = (await resp.json()).id;
  });

  test("2.2 消费累加积分 — 第一笔", async ({ request }) => {
    const resp = await request.post(`${MEMBER_URL}/api/members/${memberId}/points/earn`, {
      data: { amount: 150 },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.earned_points).toBe(150);
    expect(body.total_points).toBe(150);
  });

  test("2.3 消费累加积分 — 第二笔", async ({ request }) => {
    const resp = await request.post(`${MEMBER_URL}/api/members/${memberId}/points/earn`, {
      data: { amount: 80 },
    });
    expect(resp.status()).toBe(200);
    expect((await resp.json()).total_points).toBe(230);
  });

  test("2.4 查询积分余额与等级权益", async ({ request }) => {
    const resp = await request.get(`${MEMBER_URL}/api/members/${memberId}/points`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.points).toBe(230);
    expect(body.level).toBe("NORMAL");
    expect(body.level_benefits).toHaveProperty("discount");
  });

  test("2.5 积分兑换", async ({ request }) => {
    const resp = await request.post(`${MEMBER_URL}/api/members/${memberId}/points/redeem`, {
      data: { points: 100 },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.redeemed_points).toBe(100);
    expect(body.remaining_points).toBe(130);
  });

  test("2.6 兑换后积分余额正确", async ({ request }) => {
    const resp = await request.get(`${MEMBER_URL}/api/members/${memberId}/points`);
    expect(resp.status()).toBe(200);
    expect((await resp.json()).points).toBe(130);
  });

  test("2.7 超额兑换应返回 400", async ({ request }) => {
    const resp = await request.post(`${MEMBER_URL}/api/members/${memberId}/points/redeem`, {
      data: { points: 99999 },
    });
    expect(resp.status()).toBe(400);
    expect((await resp.json()).error).toMatch(/积分不足/);
  });
});

// ============================================================
// Journey 3: 冲突处理与多用户并发
// (任务书要求: 店员后台 → 接单 → 调度桌位 → 完单 → 看板更新)
// 注: 店员后台/接单/看板为规划中功能，当前用并发冲突场景替代验证系统健壮性
// ============================================================

test.describe("Journey 3: 多用户并发预约与冲突恢复", () => {
  const resvDate = futureDate(3);
  let firstReservationId;

  test("3.1 用户 A 成功预约桌位 1", async ({ request }) => {
    const resp = await request.post(`${RESERVATION_URL}/api/reservations`, {
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
    firstReservationId = (await resp.json()).id;
  });

  test("3.2 用户 B 同桌位同时段应返回 409 冲突", async ({ request }) => {
    const resp = await request.post(`${RESERVATION_URL}/api/reservations`, {
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

  test("3.3 用户 B 改约其他桌位成功", async ({ request }) => {
    const resp = await request.post(`${RESERVATION_URL}/api/reservations`, {
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

  test("3.4 用户 A 取消预约释放时段", async ({ request }) => {
    const resp = await request.delete(`${RESERVATION_URL}/api/reservations/${firstReservationId}`);
    expect(resp.status()).toBe(204);
  });

  test("3.5 用户 C 可以预约被释放的桌位时段", async ({ request }) => {
    const resp = await request.post(`${RESERVATION_URL}/api/reservations`, {
      data: {
        member_id: uid(),
        store_id: 1,
        table_id: 1,
        reservation_date: resvDate,
        start_time: "15:00",
        guest_count: 3,
      },
    });
    expect(resp.status()).toBe(201);
  });

  test("3.6 查询该时段所有桌位状态", async ({ request }) => {
    const resp = await request.get(`${RESERVATION_URL}/api/reservations/available`, {
      params: { store_id: 1, reservation_date: resvDate, guest_count: 2 },
    });
    expect(resp.status()).toBe(200);
    const slots = await resp.json();
    // 桌位 1 和 2 的 15:00 时段已被占用，其余时段应可用
    const occupiedAt15 = slots.filter(
      (s) => s.start_time === "15:00:00" && [1, 2].includes(s.table_id)
    );
    expect(occupiedAt15.length).toBe(0);
  });
});
