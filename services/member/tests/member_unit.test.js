/**
 * 会员服务单元测试 (6 条)
 * TC-031 ~ TC-037
 */

const request = require("supertest");

// ── Mock pg Pool before importing app ──
const mockQuery = jest.fn();
jest.mock("pg", () => ({
  Pool: jest.fn(() => ({ query: mockQuery })),
}));

// ── Mock redis before importing app ──
const mockRedisGet = jest.fn().mockResolvedValue(null);
const mockRedisSetEx = jest.fn().mockResolvedValue("OK");
const mockRedisDel = jest.fn().mockResolvedValue(1);
jest.mock("redis", () => ({
  createClient: jest.fn(() => ({
    on: jest.fn(),
    connect: jest.fn().mockResolvedValue(undefined),
    get: mockRedisGet,
    setEx: mockRedisSetEx,
    del: mockRedisDel,
  })),
}));

const { app, validatePasswordStrength } = require("../src/index");

beforeEach(() => {
  mockQuery.mockReset();
  mockRedisGet.mockReset().mockResolvedValue(null);
});

// ============================================================
// TC-031: 会员注册 — 正常注册应返回 201
// ============================================================

describe("TC-031 会员注册", () => {
  test("提供 name + phone 应注册成功并返回 201", async () => {
    // 模拟: 手机号未注册
    mockQuery
      .mockResolvedValueOnce({ rows: [] }) // SELECT 查重
      .mockResolvedValueOnce({
        rows: [
          {
            id: 1,
            name: "张三",
            phone: "13800001111",
            email: "zhang@test.com",
            password: "",
            level: "NORMAL",
            points: 0,
            total_spent: "0",
            preferences: null,
            created_at: new Date(),
          },
        ],
      }); // INSERT

    const res = await request(app)
      .post("/api/members")
      .send({ name: "张三", phone: "13800001111", email: "zhang@test.com" });

    expect(res.status).toBe(201);
    expect(res.body.name).toBe("张三");
    expect(res.body.phone).toBe("13800001111");
    expect(res.body.id).toBeDefined();
  });
});

// ============================================================
// TC-032: 手机号重复 — 重复注册应返回 409
// ============================================================

describe("TC-032 手机号重复", () => {
  test("已注册的手机号再次注册应返回 409", async () => {
    // 模拟: 手机号已存在
    mockQuery.mockResolvedValueOnce({ rows: [{ id: 1 }] });

    const res = await request(app)
      .post("/api/members")
      .send({ name: "张三", phone: "13800001111" });

    expect(res.status).toBe(409);
    expect(res.body.error).toMatch(/已注册/);
  });
});

// ============================================================
// TC-033: 密码强度 — 弱密码应返回 400
// ============================================================

describe("TC-033 密码强度", () => {
  test("密码不足 8 位应返回 400", async () => {
    const res = await request(app)
      .post("/api/members")
      .send({ name: "李四", phone: "13900002222", password: "Ab1" });

    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/密码/);
  });

  test("密码缺少大写字母应返回 400", async () => {
    const res = await request(app)
      .post("/api/members")
      .send({ name: "李四", phone: "13900002222", password: "abcdefg1" });

    expect(res.status).toBe(400);
  });

  test("密码缺少小写字母应返回 400", async () => {
    const res = await request(app)
      .post("/api/members")
      .send({ name: "李四", phone: "13900002222", password: "ABCDEFG1" });

    expect(res.status).toBe(400);
  });

  test("密码缺少数字应返回 400", async () => {
    const res = await request(app)
      .post("/api/members")
      .send({ name: "李四", phone: "13900002222", password: "Abcdefgh" });

    expect(res.status).toBe(400);
  });

  test("强密码 (8位+大小写+数字) 应通过验证", async () => {
    mockQuery
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({
        rows: [
          {
            id: 2,
            name: "李四",
            phone: "13900002222",
            email: null,
            password: "TestPass1",
            level: "NORMAL",
            points: 0,
            total_spent: "0",
            preferences: null,
            created_at: new Date(),
          },
        ],
      });

    const res = await request(app)
      .post("/api/members")
      .send({ name: "李四", phone: "13900002222", password: "TestPass1" });

    expect(res.status).toBe(201);
  });

  test("validatePasswordStrength 纯函数测试", () => {
    expect(validatePasswordStrength("Ab1")).toBe(false);
    expect(validatePasswordStrength("abcdefgh1")).toBe(false);
    expect(validatePasswordStrength("ABCDEFGH1")).toBe(false);
    expect(validatePasswordStrength("Abcdefgh")).toBe(false);
    expect(validatePasswordStrength("TestPass1")).toBe(true);
    expect(validatePasswordStrength("MyP@ssw0rd")).toBe(true);
  });
});

// ============================================================
// TC-035: 积分兑换 — 正常兑换应扣减积分
// ============================================================

describe("TC-035 积分兑换", () => {
  test("积分充足时兑换应成功", async () => {
    // UPDATE ... WHERE points >= 200 RETURNING * → 返回扣减后的结果
    mockQuery.mockResolvedValueOnce({ rows: [{ id: 1, points: 300 }], rowCount: 1 });

    const res = await request(app)
      .post("/api/members/1/points/redeem")
      .send({ points: 200 });

    expect(res.status).toBe(200);
    expect(res.body.redeemed_points).toBe(200);
    expect(res.body.remaining_points).toBe(300);
  });
});

// ============================================================
// TC-036: 积分不足 — 余额不够应返回 400
// ============================================================

describe("TC-036 积分不足", () => {
  test("积分余额小于兑换数量应返回 400", async () => {
    // UPDATE 返回空行（WHERE points >= 200 不满足）
    mockQuery.mockResolvedValueOnce({ rows: [], rowCount: 0 });
    // SELECT 查会员存在
    mockQuery.mockResolvedValueOnce({ rows: [{ id: 1 }], rowCount: 1 });

    const res = await request(app)
      .post("/api/members/1/points/redeem")
      .send({ points: 200 });

    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/积分不足/);
  });

  test("会员不存在应返回 404", async () => {
    // UPDATE 返回空行
    mockQuery.mockResolvedValueOnce({ rows: [], rowCount: 0 });
    // SELECT 也返回空行（会员不存在）
    mockQuery.mockResolvedValueOnce({ rows: [], rowCount: 0 });

    const res = await request(app)
      .post("/api/members/99999/points/redeem")
      .send({ points: 100 });

    expect(res.status).toBe(404);
  });
});

// ============================================================
// TC-037: 兑换负数 — 负数积分应返回 400
// ============================================================

describe("TC-037 兑换负数", () => {
  test("兑换负数积分应返回 400", async () => {
    const res = await request(app)
      .post("/api/members/1/points/redeem")
      .send({ points: -50 });

    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/大于 0/);
  });

  test("兑换 0 积分应返回 400", async () => {
    const res = await request(app)
      .post("/api/members/1/points/redeem")
      .send({ points: 0 });

    expect(res.status).toBe(400);
  });

  test("不传 points 字段应返回 400", async () => {
    const res = await request(app)
      .post("/api/members/1/points/redeem")
      .send({});

    expect(res.status).toBe(400);
  });
});
