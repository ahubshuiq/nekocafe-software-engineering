/**
 * Lighthouse CI 配置 — 可访问性测试
 *
 * 运行方式:
 *   1. 安装: npm install -g @lhci/cli
 *   2. 启动前端: docker compose up -d
 *   3. 执行: lhci autorun --config=tests/a11y/lighthouse.config.js
 *
 * 前端部署后，将 FRONTEND_URL 替换为实际地址。
 */

module.exports = {
  ci: {
    collect: {
      url: [
        process.env.FRONTEND_URL || "http://localhost:5173/",
        (process.env.FRONTEND_URL || "http://localhost:5173") + "/reservation",
        (process.env.FRONTEND_URL || "http://localhost:5173") + "/member",
      ],
      numberOfRuns: 1,
      settings: {
        preset: "desktop",
        chromeFlags: "--no-sandbox --headless",
      },
    },
    assert: {
      assertions: {
        "categories:accessibility": ["error", { minScore: 0.9 }],
        "categories:performance": ["warn", { minScore: 0.7 }],
        "categories:best-practices": ["warn", { minScore: 0.8 }],
        "categories:seo": ["warn", { minScore: 0.8 }],
      },
    },
    upload: {
      target: "temporary-public-storage",
    },
  },
};
