import { defineConfig, devices } from "@playwright/test";

// E2E do POS (backend-independente). Sobe um mock backend leve + o app (build de
// produção servido em baseURL '/') para exercitar comportamentos que NÃO dependem de
// dados de negócio: gate de login (sessão de operador ausente → terminal 401) e banner
// offline. Fluxos com dados ricos (comanda→pagamento→cozinha, lock screen, re-gate de
// 401 no meio da sessão) rodam contra o Django real (reviewer local) — ver tests/e2e/README.
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.ts",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:3002",
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
      // Build com baseURL '/' (produção usa '/pos/') + serve o Nitro. reuseExistingServer
      // evita rebuild a cada corrida local.
      command: "nuxt build && node .output/server/index.mjs",
      port: 3002,
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
      env: {
        NUXT_APP_BASE_URL: "/",
        NUXT_DJANGO_BASE_URL: "http://127.0.0.1:8798",
        HOST: "127.0.0.1",
        PORT: "3002",
      },
    },
  ],
});
