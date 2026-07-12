import { defineConfig, devices } from "@playwright/test";

// E2E do KDS (backend-independente). O mock ramifica pelo cookie `e2e_session` que o BFF
// encaminha: telas de operador atrás do gate; o painel público `/pickup` renderiza sem
// sessão. Build com baseURL '/' (produção usa '/kds/'). Login/lock/ações reais rodam
// contra o Django real (reviewer local) — ver tests/e2e/README. Porta de e2e dedicada
// (3103) para não reusar o dev server em :3003; mock :8798.
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.ts",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:3103",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node tests/e2e/mockBackend.mjs",
      port: 8798,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "nuxt build && node .output/server/index.mjs",
      port: 3103,
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
      env: {
        NUXT_APP_BASE_URL: "/",
        NUXT_DJANGO_BASE_URL: "http://127.0.0.1:8798",
        HOST: "127.0.0.1",
        PORT: "3103",
      },
    },
  ],
});
