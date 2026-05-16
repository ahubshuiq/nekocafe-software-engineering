/**
 * NekoCafe 会员服务 (Member Service)
 * 注册登录、积分等级、跨门店统一会员
 */

const express = require("express");
const cors = require("cors");
const helmet = require("helmet");
const crypto = require("crypto");
const { Pool } = require("pg");
const redis = require("redis");
const bcrypt = require("bcrypt");

// ======================== 配置 ========================

const PORT = process.env.PORT || 3000;
const DATABASE_URL = process.env.DATABASE_URL;
const REDIS_URL = process.env.REDIS_URL;

// ======================== 数据库 ========================

const pool = new Pool({
  connectionString: DATABASE_URL,
  max: parseInt(process.env.DB_POOL_MAX || "20"),
  connectionTimeoutMillis: 5000,
  idleTimeoutMillis: 30000,
});

// ======================== Redis ========================

let redisClient;
let redisReady = false;

async function connectRedis() {
  redisClient = redis.createClient({ url: REDIS_URL });
  redisClient.on("error", (err) => console.error(JSON.stringify({ timestamp: new Date().toISOString(), level: "error", service: "member", msg: "Redis error", error: err.message })));
  await redisClient.connect();
  redisReady = true;
  console.log(JSON.stringify({ timestamp: new Date().toISOString(), level: "info", service: "member", msg: "Redis connected" }));
}

// ======================== 初始化表 ========================

async function initDB() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS member (
      id              SERIAL PRIMARY KEY,
      name            VARCHAR(64) NOT NULL,
      phone           VARCHAR(20) UNIQUE NOT NULL,
      password        VARCHAR(256) NOT NULL DEFAULT '',
      email           VARCHAR(128),
      avatar          VARCHAR(256),
      level           VARCHAR(20) NOT NULL DEFAULT 'NORMAL',
      points          INTEGER NOT NULL DEFAULT 0,
      total_spent     NUMERIC(12,2) NOT NULL DEFAULT 0,
      preferences     JSONB,
      created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
      updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
    );
  `);
  console.log(JSON.stringify({ timestamp: new Date().toISOString(), level: "info", service: "member", msg: "Member table ready" }));
}

// ======================== 工具函数 ========================

/**
 * 校验密码强度：至少 8 位，须含大小写字母和数字
 */
function validatePasswordStrength(password) {
  if (!password || password.length < 8) return false;
  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasDigit = /[0-9]/.test(password);
  return hasUpper && hasLower && hasDigit;
}

// ======================== Express 应用 ========================

const CORS_ORIGINS = process.env.CORS_ORIGINS
  ? process.env.CORS_ORIGINS.split(",")
  : ["http://localhost:3000", "http://localhost:5173"];

const app = express();
app.use(cors({ origin: CORS_ORIGINS }));
app.use(helmet());

// 结构化 JSON 日志中间件（含 traceId）
app.use((req, res, next) => {
  const traceId = req.headers["x-trace-id"] || crypto.randomUUID();
  req.traceId = traceId;
  const start = Date.now();
  res.on("finish", () => {
    const log = JSON.stringify({
      timestamp: new Date().toISOString(),
      level: res.statusCode >= 500 ? "error" : res.statusCode >= 400 ? "warn" : "info",
      service: "member",
      traceId,
      method: req.method,
      path: req.originalUrl,
      status: res.statusCode,
      responseTime: Date.now() - start,
    });
    console.log(log);
  });
  next();
});

app.use(express.json());

// ---------- 健康检查 ----------

app.get("/health", (req, res) => {
  res.json({
    status: "UP",
    service: "member-service",
    timestamp: new Date().toISOString(),
  });
});

// ---------- 注册会员 ----------

app.post("/api/members", async (req, res) => {
  try {
    const { name, phone, email, password } = req.body;
    if (!name || !phone) {
      return res.status(400).json({ error: "姓名和手机号为必填项" });
    }

    if (!/^1[3-9]\d{9}$/.test(phone)) {
      return res.status(400).json({ error: "手机号格式不正确" });
    }

    if (password && !validatePasswordStrength(password)) {
      return res.status(400).json({ error: "密码须至少 8 位且含大小写字母和数字" });
    }

    const existing = await pool.query(
      "SELECT id FROM member WHERE phone = $1",
      [phone]
    );
    if (existing.rows.length > 0) {
      return res.status(409).json({ error: "该手机号已注册" });
    }

    const hashedPassword = password ? await bcrypt.hash(password, 12) : '';
    const result = await pool.query(
      `INSERT INTO member (name, phone, email, password) VALUES ($1, $2, $3, $4) RETURNING *`,
      [name, phone, email || null, hashedPassword]
    );

    const member = result.rows[0];
    console.log(JSON.stringify({ timestamp: new Date().toISOString(), level: "info", service: "member", traceId: req.traceId, msg: "Member registered", memberId: member.id }));
    res.status(201).json(formatMember(member));
  } catch (err) {
    console.error(JSON.stringify({ timestamp: new Date().toISOString(), level: "error", service: "member", traceId: req.traceId, msg: "Register error", error: err.message }));
    res.status(500).json({ error: "注册失败" });
  }
});

// ---------- 查询会员信息 ----------

app.get("/api/members/:id", async (req, res) => {
  try {
    const { id } = req.params;

    const cached = redisReady ? await redisClient.get(`member:${id}`) : null;
    if (cached) return res.json(JSON.parse(cached));

    const result = await pool.query("SELECT * FROM member WHERE id = $1", [id]);
    if (result.rows.length === 0) {
      return res.status(404).json({ error: "会员不存在" });
    }

    const member = formatMember(result.rows[0]);
    if (redisReady) await redisClient.setEx(`member:${id}`, 300, JSON.stringify(member));
    res.json(member);
  } catch (err) {
    console.error(JSON.stringify({ timestamp: new Date().toISOString(), level: "error", service: "member", traceId: req.traceId, msg: "Get member error", error: err.message }));
    res.status(500).json({ error: "查询失败" });
  }
});

// ---------- 查询积分 ----------

app.get("/api/members/:id/points", async (req, res) => {
  try {
    const { id } = req.params;
    const result = await pool.query(
      "SELECT id, level, points, total_spent FROM member WHERE id = $1",
      [id]
    );
    if (result.rows.length === 0) {
      return res.status(404).json({ error: "会员不存在" });
    }

    const { level, points, total_spent } = result.rows[0];
    res.json({
      member_id: parseInt(id),
      level,
      points,
      total_spent: parseFloat(total_spent),
      level_benefits: getLevelBenefits(level),
    });
  } catch (err) {
    console.error(JSON.stringify({ timestamp: new Date().toISOString(), level: "error", service: "member", traceId: req.traceId, msg: "Get points error", error: err.message }));
    res.status(500).json({ error: "查询积分失败" });
  }
});

// ---------- 消费累加积分 ----------

app.post("/api/members/:id/points/earn", async (req, res) => {
  try {
    const { id } = req.params;
    const { amount } = req.body;
    if (!amount || amount <= 0) {
      return res.status(400).json({ error: "消费金额须大于 0" });
    }

    const earnedPoints = Math.floor(amount);

    const result = await pool.query(
      `UPDATE member
       SET points = points + $1,
           total_spent = total_spent + $2,
           level = CASE
             WHEN total_spent + $2 >= 10000 THEN 'BLACK'
             WHEN total_spent + $2 >= 5000  THEN 'GOLD'
             WHEN total_spent + $2 >= 2000  THEN 'SILVER'
             ELSE level
           END,
           updated_at = NOW()
       WHERE id = $3
       RETURNING *`,
      [earnedPoints, amount, id]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ error: "会员不存在" });
    }

    if (redisReady) await redisClient.del(`member:${id}`);

    const member = result.rows[0];
    console.log(JSON.stringify({ timestamp: new Date().toISOString(), level: "info", service: "member", traceId: req.traceId, msg: "Points earned", memberId: id, operation: "earn" }));
    res.json({
      member_id: parseInt(id),
      earned_points: earnedPoints,
      total_points: member.points,
      level: member.level,
    });
  } catch (err) {
    console.error(JSON.stringify({ timestamp: new Date().toISOString(), level: "error", service: "member", traceId: req.traceId, msg: "Earn points error", error: err.message }));
    res.status(500).json({ error: "积分累加失败" });
  }
});

// ---------- 积分兑换 ----------

app.post("/api/members/:id/points/redeem", async (req, res) => {
  try {
    const { id } = req.params;
    const { points: redeemPoints } = req.body;
    if (!redeemPoints || redeemPoints <= 0) {
      return res.status(400).json({ error: "兑换积分须大于 0" });
    }

    const result = await pool.query(
      `UPDATE member SET points = points - $1, updated_at = NOW() WHERE id = $2 AND points >= $1 RETURNING *`,
      [redeemPoints, id]
    );

    if (result.rows.length === 0) {
      const exists = await pool.query("SELECT id FROM member WHERE id = $1", [id]);
      if (exists.rows.length === 0) {
        return res.status(404).json({ error: "会员不存在" });
      }
      return res.status(400).json({ error: "积分不足" });
    }

    if (redisReady) await redisClient.del(`member:${id}`);

    const member = result.rows[0];
    console.log(JSON.stringify({ timestamp: new Date().toISOString(), level: "info", service: "member", traceId: req.traceId, msg: "Points redeemed", memberId: id, operation: "redeem" }));
    res.json({
      member_id: parseInt(id),
      redeemed_points: redeemPoints,
      remaining_points: member.points,
    });
  } catch (err) {
    console.error(JSON.stringify({ timestamp: new Date().toISOString(), level: "error", service: "member", traceId: req.traceId, msg: "Redeem points error", error: err.message }));
    res.status(500).json({ error: "积分兑换失败" });
  }
});

// ---------- 等级权益 ----------

function getLevelBenefits(level) {
  const benefits = {
    NORMAL: { discount: "无折扣", freeDessert: false, priorityBooking: false },
    SILVER: { discount: "95折",  freeDessert: false, priorityBooking: false },
    GOLD:   { discount: "9折",   freeDessert: true,  priorityBooking: true },
    BLACK:  { discount: "85折",  freeDessert: true,  priorityBooking: true },
  };
  return benefits[level] || benefits.NORMAL;
}

function formatMember(row) {
  return {
    id: row.id,
    name: row.name,
    phone: row.phone,
    email: row.email,
    level: row.level,
    points: row.points,
    total_spent: parseFloat(row.total_spent),
    preferences: row.preferences,
    created_at: row.created_at,
  };
}
// ======================== 启动 ========================

async function start() {
  await connectRedis();
  await initDB();
  const server = app.listen(PORT, () => {
    console.log(JSON.stringify({ timestamp: new Date().toISOString(), level: "info", service: "member", msg: `Member service running on port ${PORT}` }));
  });

  const shutdown = async () => {
    console.log(JSON.stringify({ timestamp: new Date().toISOString(), level: "info", service: "member", msg: "Shutting down" }));
    server.close();
    if (redisReady) await redisClient.quit();
    await pool.end();
    process.exit(0);
  };
  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);
}

// 核心修改：只有【直接运行 node index.js】时才启动服务
// 测试导入时，不会执行这段代码，避免端口占用！
if (require.main === module) {
  start().catch(console.error);
}

// 导出app，供测试文件使用
module.exports = { app, validatePasswordStrength, connectRedis, getRedisClient: () => redisClient };
