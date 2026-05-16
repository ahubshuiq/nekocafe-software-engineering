/**
 * 会员服务冒烟测试
 */

const request = require("supertest");
const { app } = require("../src/index");

describe("Member Service Smoke Tests", () => {
  test("GET /health returns UP", async () => {
    const res = await request(app).get("/health");
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("UP");
    expect(res.body.service).toBe("member-service");
  });

  test("POST /api/members without phone returns 400", async () => {
    const res = await request(app)
      .post("/api/members")
      .send({ name: "测试用户" });
    expect(res.status).toBe(400);
  });

  test("GET /api/members/99999 returns 404", async () => {
    const res = await request(app).get("/api/members/99999");
    expect(res.status).toBe(404);
  });

  test("GET /api/members/99999/points returns 404", async () => {
    const res = await request(app).get("/api/members/99999/points");
    expect(res.status).toBe(404);
  });

  test("POST /api/members/1/points/earn with negative amount returns 400", async () => {
    const res = await request(app)
      .post("/api/members/1/points/earn")
      .send({ amount: -10 });
    expect(res.status).toBe(400);
  });
});
